"""
로그인한 팀 전용 "우리팀 분석 > 팀 분석" 탭 데이터 조립 + team_stats_summary 캐싱.

services/my_team_stats.py(통계 탭)와 같은 전제 - Henrik을 실시간으로 부르지 않고 DB
(matches/match_player_stats)만으로 계산한다. 다만 이 탭은 round_detail_json을 라운드
단위로 파싱해야 해서 계산 비용이 훨씬 크기 때문에, 결과를 team_stats_summary에
캐싱해두고(cache-aside: 있으면 읽고, 없으면 계산해서 채운 뒤 읽음) 이후 조회는 재계산
없이 캐시만 읽는다.

라운드 단위 파생값은 Henrik 원본에 명시적인 필드가 없어 아래 방식으로 추론한다(전부
사용자 확인 후 진행하기로 한 부분 - 프로젝트 내 유일한 소스이므로 여기 문서화):
  - 공격/수비: 라운드의 player_stats[].player_team으로 "우리 팀이 이 매치에서 Red/Blue
    중 어느 색이었는지" 먼저 알아낸 뒤, 하프(12라운드)마다 그 구간에서 스파이크가 설치된
    라운드의 plant_events.planted_by.team을 그 구간 전체의 공격 팀으로 본다(발로란트
    표준 룰 - 사이드는 라운드마다 안 바뀌고 하프 단위로만 바뀜, 연장은 2라운드 단위로
    스왑). 그 구간에 설치가 한 번도 없으면 그 구간은 공수 판정 불가로 집계에서 제외한다.
  - 에코 라운드: 그 라운드 우리 팀 5명의 economy.loadout_value 평균이 ECO_THRESHOLD
    미만이면 에코로 판정한다(공식 정의가 아닌 휴리스틱 - 필요시 조정).
  - 클러치(1v1/1v2 트레이드 성공률): 라운드의 모든 kill_events를 시간순으로 재생하며
    우리 팀이 1명 남는 순간 상대가 몇 명 남아있었는지로 상황을 분류하고, 그 라운드의
    승패를 그대로 클러치 성공/실패로 본다.
  - 타격대(Duelist) vs 타격대: ml/engagement_predictor.py::_duelist_matchup_from_acs를
    그대로 재사용한다 - 승부예측 쪽(상대팀 실시간 분석)과 같은 정규화 방식으로
    "타격대 매치업 유불리"의 의미를 앱 전체에서 하나로 유지하기 위함.
  - skills(스킬 사용 유효성)는 제외한다 - Henrik 응답의 ability_casts가 항상 null로
    와서(실측 확인) 데이터 소스가 없다.
"""
import json as json_module
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, defer

from ml.engagement_predictor import _duelist_matchup_from_acs
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team_stats_summary import TeamStatsSummary
from services.my_team_stats import MATCH_HISTORY_LIMIT, _load_map_name_by_uuid
from services.player_profile import ROLE_LABELS, _load_ref_agents

# 팀 평균 loadout_value(경제력)가 이 아래면 에코 라운드로 판정하는 휴리스틱 임계값.
# 공식 정의가 아니며, 다운스케일 무기(사이드암 위주) 구간을 대략 겨냥한 값이다.
ECO_THRESHOLD = 2000

_DUELIST_LABEL = ROLE_LABELS["Duelist"]

# 콤보(선호 요원 조합)는 맵당 최대 2개까지만 캐싱한다(ComboBlock이 화면에 2개만 표시).
MAX_COMBOS = 2


def _round_segments(round_count: int) -> list[tuple[int, int]]:
    """공격/수비가 바뀌지 않는 구간 경계. 정규시간은 12라운드씩(0-11, 12-23), 연장은
    2라운드씩(24-25, 26-27, ...) 스왑하는 표준 룰을 따른다."""
    segments = []
    idx = 0
    while idx < round_count:
        end = min(idx + 12, 24, round_count) if idx < 24 else min(idx + 2, round_count)
        segments.append((idx, end))
        idx = end
    return segments


def _determine_our_color(rounds: list, our_puuids: set[str]) -> str | None:
    """rounds[i].player_stats[].player_team/player_puuid로 우리 팀이 이 매치에서
    "Red"/"Blue" 중 어느 색이었는지 확인. 라운드마다 전체 로스터의 player_stats가 항상
    있어서(액션 여부와 무관) 첫 라운드에서 대부분 바로 확정된다."""
    for rnd in rounds:
        for ps in (rnd.get("player_stats") or []):
            if ps.get("player_puuid") in our_puuids and ps.get("player_team"):
                return ps["player_team"]
    return None


def _segment_attackers(rounds: list, segments: list[tuple[int, int]]) -> dict[tuple[int, int], str | None]:
    result: dict[tuple[int, int], str | None] = {}
    for seg in segments:
        attacker = None
        for i in range(seg[0], seg[1]):
            rnd = rounds[i]
            if rnd.get("bomb_planted"):
                planted_by = (rnd.get("plant_events") or {}).get("planted_by") or {}
                if planted_by.get("team"):
                    attacker = planted_by["team"]
                    break
        result[seg] = attacker
    return result


def _round_kill_events(rnd: dict) -> list[dict]:
    """라운드 하나의 모든 킬 이벤트를 시간순으로. player_stats[].kill_events는 그
    선수 본인이 낸 킬만 담고 있어 전체를 모으려면 로스터 전원의 목록을 합쳐야 한다."""
    events: list[dict] = []
    for ps in (rnd.get("player_stats") or []):
        events.extend(ps.get("kill_events") or [])
    return sorted(events, key=lambda k: k.get("kill_time_in_round") or 0)


def _analyze_rounds(rounds: list, our_color: str) -> list[dict]:
    segments = _round_segments(len(rounds))
    attackers = _segment_attackers(rounds, segments)

    records = []
    for i, rnd in enumerate(rounds):
        seg = next(s for s in segments if s[0] <= i < s[1])
        attacker = attackers[seg]
        we_attacked = None if attacker is None else (attacker == our_color)

        winning_team = rnd.get("winning_team")
        we_won = None if not winning_team else (winning_team == our_color)

        our_loadouts = [
            (ps.get("economy") or {}).get("loadout_value")
            for ps in (rnd.get("player_stats") or [])
            if ps.get("player_team") == our_color and (ps.get("economy") or {}).get("loadout_value") is not None
        ]
        is_eco = (sum(our_loadouts) / len(our_loadouts) < ECO_THRESHOLD) if our_loadouts else None

        kills = _round_kill_events(rnd)
        opening = kills[0] if kills else None
        got_fb = (opening.get("killer_team") == our_color) if opening else None
        got_fd = (opening.get("victim_team") == our_color) if opening else None

        plant = rnd.get("plant_events") or {}
        planted_by = plant.get("planted_by") or {}
        we_planted = bool(planted_by.get("team")) and planted_by.get("team") == our_color
        plant_site = plant.get("plant_site") if we_planted else None
        plant_time = plant.get("plant_time_in_round") if we_planted else None

        records.append({
            "we_won": we_won,
            "we_attacked": we_attacked,
            "is_pistol": i in (0, 12),
            "is_eco": is_eco,
            "got_fb": got_fb,
            "got_fd": got_fd,
            "plant_site": plant_site,
            "plant_time_ms": plant_time,
        })
    return records


def _clutch_tally(rounds: list, our_puuids: set[str], opp_puuids: set[str], our_color: str) -> dict[int, dict]:
    """라운드마다 우리 팀이 1명 남는 순간 상대가 몇 명 남아있었는지로 클러치 상황(1/2)을
    분류하고, 그 라운드의 승패를 클러치 성공/실패로 집계."""
    result = {1: {"win": 0, "loss": 0}, 2: {"win": 0, "loss": 0}}
    for rnd in rounds:
        kills = _round_kill_events(rnd)
        if not kills:
            continue
        our_alive = set(our_puuids)
        opp_alive = set(opp_puuids)
        clutch_n = None
        for k in kills:
            victim = k.get("victim_puuid")
            our_alive.discard(victim)
            opp_alive.discard(victim)
            if clutch_n is None and len(our_alive) == 1 and len(opp_alive) >= 1:
                clutch_n = len(opp_alive)
        if clutch_n in (1, 2):
            won = rnd.get("winning_team") == our_color
            result[clutch_n]["win" if won else "loss"] += 1
    return result


def _pct(wins: int, losses: int) -> int:
    total = wins + losses
    return round(wins / total * 100) if total else 0


def _aggregate_round_phase(records: list[dict]) -> dict:
    atk_w = atk_l = def_w = def_l = pistol_w = pistol_l = eco_w = eco_l = 0
    fb_rounds = fb_wins = fd_rounds = fd_losses = 0
    for r in records:
        if r["we_won"] is not None:
            if r["we_attacked"] is True:
                atk_w += r["we_won"]
                atk_l += not r["we_won"]
            elif r["we_attacked"] is False:
                def_w += r["we_won"]
                def_l += not r["we_won"]
            if r["is_pistol"]:
                pistol_w += r["we_won"]
                pistol_l += not r["we_won"]
            if r["is_eco"]:
                eco_w += r["we_won"]
                eco_l += not r["we_won"]
        if r["got_fb"]:
            fb_rounds += 1
            fb_wins += bool(r["we_won"])
        if r["got_fd"]:
            fd_rounds += 1
            fd_losses += r["we_won"] is False

    return {
        "atkWinRate": _pct(atk_w, atk_l),
        "defWinRate": _pct(def_w, def_l),
        "pistolWinRate": _pct(pistol_w, pistol_l),
        "ecoWinRate": _pct(eco_w, eco_l),
        "fbWinPct": round(fb_wins / fb_rounds * 100) if fb_rounds else 0,
        "fdLosePct": round(fd_losses / fd_rounds * 100) if fd_rounds else 0,
    }, atk_w + def_w, atk_l + def_l


def _upsert_summary_row(
    db: Session, team_id: str, stat_type: str, dimension_key: str, wins: int, losses: int, metrics: dict
) -> None:
    row = (
        db.query(TeamStatsSummary)
        .filter(
            TeamStatsSummary.team_id == team_id,
            TeamStatsSummary.stat_type == stat_type,
            TeamStatsSummary.dimension_key == dimension_key,
        )
        .first()
    )
    if row is None:
        row = TeamStatsSummary(team_id=team_id, stat_type=stat_type, dimension_key=dimension_key)
        db.add(row)
    row.wins = wins
    row.losses = losses
    row.metrics_json = metrics


def _compute_and_cache(db: Session, team_id: str) -> None:
    # services/my_team_stats.py와 동일한 이유(OR + ORDER BY가 round_detail_json까지
    # 정렬 버퍼에 올려 "Out of sort memory"가 남)로 가벼운 컬럼만 먼저 조회하고
    # round_detail_json은 정렬이 필요 없는 IN 조회로 별도로 채운다.
    base_query = db.query(Match).options(defer(Match.round_detail_json))
    matches_by_id = {
        m.match_id: m
        for m in (
            base_query.filter(Match.team_a_id == team_id).all()
            + base_query.filter(Match.team_b_id == team_id).all()
        )
    }
    matches = sorted(matches_by_id.values(), key=lambda m: m.game_start or datetime.min, reverse=True)[
        :MATCH_HISTORY_LIMIT
    ]
    match_ids = [m.match_id for m in matches]

    detail_by_id: dict[str, list] = {}
    if match_ids:
        stmt = text("SELECT match_id, round_detail_json FROM matches WHERE match_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        for r in db.execute(stmt, {"ids": match_ids}).mappings().all():
            raw = r["round_detail_json"]
            parsed = json_module.loads(raw) if isinstance(raw, str) else raw
            detail_by_id[r["match_id"]] = parsed if isinstance(parsed, list) else []

    stats_rows = (
        db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id.in_(match_ids)).all() if match_ids else []
    )
    by_match: dict[str, list[MatchPlayerStat]] = {}
    for s in stats_rows:
        by_match.setdefault(s.match_id, []).append(s)

    map_names = _load_map_name_by_uuid(db)
    agents = _load_ref_agents(db)

    all_records: list[dict] = []
    clutch_totals = {1: {"win": 0, "loss": 0}, 2: {"win": 0, "loss": 0}}
    our_duelist_acs: list[int] = []
    opp_duelist_acs: list[int] = []
    map_buckets: dict[str, dict] = {}

    for match in matches:
        rounds = detail_by_id.get(match.match_id)
        if not rounds:
            continue
        roster = by_match.get(match.match_id) or []
        our_rows = [r for r in roster if r.team_id == team_id]
        opp_rows = [r for r in roster if r.team_id != team_id]
        if not our_rows:
            continue
        our_puuids = {r.puuid for r in our_rows}
        opp_puuids = {r.puuid for r in opp_rows}

        our_color = _determine_our_color(rounds, our_puuids)
        if our_color is None:
            continue  # 방어적 스킵 - 이 매치는 공수/승패 판정 불가

        records = _analyze_rounds(rounds, our_color)
        all_records.extend(records)

        clutch = _clutch_tally(rounds, our_puuids, opp_puuids, our_color)
        for n in (1, 2):
            clutch_totals[n]["win"] += clutch[n]["win"]
            clutch_totals[n]["loss"] += clutch[n]["loss"]

        for r in our_rows:
            if r.role_type == _DUELIST_LABEL and r.acs is not None:
                our_duelist_acs.append(r.acs)
        for r in opp_rows:
            if r.role_type == _DUELIST_LABEL and r.acs is not None:
                opp_duelist_acs.append(r.acs)

        # --- 맵별 집계 ---
        map_uuid_key = (match.map_uuid or "").lower()
        bucket = map_buckets.setdefault(map_uuid_key, {
            "win": 0, "lose": 0,
            "atk_w": 0, "atk_l": 0, "def_w": 0, "def_l": 0,
            "site_counts": {}, "plant_times": [],
            "combos": {}, "players": {},
        })

        is_team_a = match.team_a_id == team_id
        our_rounds_won = (match.rounds_won_a if is_team_a else match.rounds_won_b) or 0
        opp_rounds_won = (match.rounds_won_b if is_team_a else match.rounds_won_a) or 0
        rounds_played = our_rounds_won + opp_rounds_won
        result = "win" if match.winner_team_id == team_id else "lose"
        bucket["win" if result == "win" else "lose"] += 1

        for rec in records:
            if rec["we_won"] is None:
                continue
            if rec["we_attacked"] is True:
                bucket["atk_w" if rec["we_won"] else "atk_l"] += 1
            elif rec["we_attacked"] is False:
                bucket["def_w" if rec["we_won"] else "def_l"] += 1
            if rec["plant_site"]:
                bucket["site_counts"][rec["plant_site"]] = bucket["site_counts"].get(rec["plant_site"], 0) + 1
            if rec["plant_time_ms"]:
                try:
                    bucket["plant_times"].append(int(rec["plant_time_ms"]))
                except (TypeError, ValueError):
                    pass

        agent_names = [
            (agents["by_uuid"].get((r.agent_uuid or "").lower()) or {}).get("name_ko") or "-"
            for r in our_rows
        ]
        if len(agent_names) == 5:
            combo_key = tuple(sorted(agent_names))
            combo = bucket["combos"].setdefault(combo_key, {"wins": 0, "total": 0})
            combo["total"] += 1
            combo["wins"] += result == "win"

        for r in our_rows:
            pbucket = bucket["players"].setdefault(
                r.puuid, {"name": None, "acs_sum": 0, "acs_n": 0, "fd_sum": 0, "rounds_sum": 0}
            )
            if r.acs is not None:
                pbucket["acs_sum"] += r.acs
                pbucket["acs_n"] += 1
            pbucket["fd_sum"] += r.first_deaths or 0
            pbucket["rounds_sum"] += rounds_played

    # puuid -> riot_name (BEST/WORST 표시용)
    all_puuids = {puuid for b in map_buckets.values() for puuid in b["players"]}
    riot_names: dict[str, str] = {}
    if all_puuids:
        riot_names = {
            r.puuid: r.riot_name
            for r in db.query(RiotAccount).filter(RiotAccount.puuid.in_(all_puuids)).all()
        }

    # --- ① 라운드 정보(전체) 캐싱 ---
    round_phase_metrics, overall_wins, overall_losses = _aggregate_round_phase(all_records)
    _upsert_summary_row(db, team_id, "round_phase", "overall", overall_wins, overall_losses, round_phase_metrics)

    # --- ③ 교전 정보 캐싱 ---
    our_duelist_avg = sum(our_duelist_acs) / len(our_duelist_acs) if our_duelist_acs else 0.0
    opp_duelist_avg = sum(opp_duelist_acs) / len(opp_duelist_acs) if opp_duelist_acs else 0.0
    matchup = _duelist_matchup_from_acs(our_duelist_avg, opp_duelist_avg)
    engagement_metrics = {
        "trade1v1": _pct(clutch_totals[1]["win"], clutch_totals[1]["loss"]),
        "trade1v2": _pct(clutch_totals[2]["win"], clutch_totals[2]["loss"]),
        "duelistVsDuelist": {"us": matchup["ourScore"], "them": matchup["theirScore"]},
    }
    _upsert_summary_row(db, team_id, "engagement", "overall", 0, 0, engagement_metrics)

    # --- ② 맵 정보 캐싱 (맵당 1행) ---
    for map_uuid_key, b in map_buckets.items():
        games = b["win"] + b["lose"]
        if games <= 0 or not map_uuid_key:
            continue

        total_plants = sum(b["site_counts"].values())
        preferred_site = (
            {site: round(cnt / total_plants * 100) for site, cnt in b["site_counts"].items()}
            if total_plants
            else {}
        )
        avg_plant_sec = round(sum(b["plant_times"]) / len(b["plant_times"]) / 1000) if b["plant_times"] else 0

        combos_sorted = sorted(
            (
                {"agents": list(k), "winRate": round(v["wins"] / v["total"] * 100), "games": v["total"]}
                for k, v in b["combos"].items()
            ),
            key=lambda x: (x["winRate"], x["games"]),
            reverse=True,
        )[:MAX_COMBOS]

        player_summaries = []
        for puuid, pb in b["players"].items():
            avg_acs = round(pb["acs_sum"] / pb["acs_n"]) if pb["acs_n"] else 0
            fd_rate = round(pb["fd_sum"] / pb["rounds_sum"] * 100) if pb["rounds_sum"] else 0
            player_summaries.append({"name": riot_names.get(puuid, "-"), "acs": avg_acs, "fd": fd_rate})

        best = max(player_summaries, key=lambda p: p["acs"], default=None)
        worst = max(player_summaries, key=lambda p: p["fd"], default=None)

        metrics = {
            "mapName": map_names.get(map_uuid_key, "-"),
            "mapWinRate": _pct(b["win"], b["lose"]),
            "atkWinRate": _pct(b["atk_w"], b["atk_l"]),
            "defWinRate": _pct(b["def_w"], b["def_l"]),
            "preferredSite": preferred_site,
            "avgSpikePlantTime": avg_plant_sec,
            "matchSample": games,
            "combos": combos_sorted,
            "comboAce": [{"name": best["name"], "acs": best["acs"]}] if best else [],
            "comboWeakness": [{"name": worst["name"], "fd": worst["fd"], "acs": worst["acs"]}] if worst else [],
        }
        _upsert_summary_row(db, team_id, "map_side", map_uuid_key, b["win"], b["lose"], metrics)

    db.commit()


def build_my_team_analysis(db: Session, team_id: str) -> dict:
    """캐시(team_stats_summary)가 있으면 그대로 읽고, 없으면(첫 진입) 계산해서 채운 뒤
    읽는다."""
    rows = db.query(TeamStatsSummary).filter(TeamStatsSummary.team_id == team_id).all()
    if not rows:
        _compute_and_cache(db, team_id)
        rows = db.query(TeamStatsSummary).filter(TeamStatsSummary.team_id == team_id).all()

    round_info: dict = {}
    engagement_info: dict | None = None
    map_info: dict = {}

    for row in rows:
        if row.stat_type == "round_phase" and row.dimension_key == "overall":
            round_info = row.metrics_json or {}
        elif row.stat_type == "engagement" and row.dimension_key == "overall":
            engagement_info = row.metrics_json or None
        elif row.stat_type == "map_side":
            metrics = dict(row.metrics_json or {})
            map_name = metrics.pop("mapName", row.dimension_key)
            map_info[map_name] = metrics

    return {
        "roundInfo": round_info,
        "mapInfoByMap": map_info,
        "engagementInfo": engagement_info,
    }
