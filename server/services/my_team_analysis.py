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
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, defer

from ml.engagement_predictor import _duelist_matchup_from_acs
from services.death_hotspot_service import compute_player_hotspots
from services.map_coords_service import normalize_location
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team_stats_summary import TeamStatsSummary
from services.my_team_stats import MATCH_HISTORY_LIMIT, _load_map_name_by_uuid
from services.player_profile import ROLE_LABELS, _load_ref_agents
from services.round_phase_analysis import (
    aggregate_round_phase,
    analyze_rounds,
    determine_team_color,
    pct,
    round_kill_events,
)

_DUELIST_LABEL = ROLE_LABELS["Duelist"]


def _clutch_tally(rounds: list, our_puuids: set[str], opp_puuids: set[str], our_color: str) -> dict[int, dict]:
    """라운드마다 우리 팀이 1명 남는 순간 상대가 몇 명 남아있었는지로 클러치 상황(1/2)을
    분류하고, 그 라운드의 승패를 클러치 성공/실패로 집계."""
    result = {1: {"win": 0, "loss": 0}, 2: {"win": 0, "loss": 0}}
    for rnd in rounds:
        kills = round_kill_events(rnd)
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


def _death_locations_for_match(rounds: list, our_puuids: set[str], map_uuid: str | None) -> list[dict]:
    """매치 하나의 모든 라운드에서 우리 팀 로스터가 사망한 위치 좌표(0~100 정규화) + puuid
    리스트. round_detail_json에 rounds 원본이 그대로 저장돼 있어(services/match_history.py::
    upsert_match_history 참고) Henrik의 kill_events[].victim_death_location을 꺼낼 수
    있지만, 이건 게임 월드 좌표라 그대로는 미니맵 위에 못 찍는다 - services/map_coords_
    service.py::normalize_location으로 변환한다. 맵별로 모아 선수별 최다 사망 위치
    (히트맵)를 계산하는 재료로 쓴다(services/death_hotspot_service.py::
    compute_player_hotspots). 변환 계수를 못 찾은 좌표(map_uuid가 없거나 신규/구버전
    맵)는 조용히 스킵한다."""
    locations: list[dict] = []
    for rnd in rounds:
        for k in round_kill_events(rnd):
            puuid = k.get("victim_puuid")
            if puuid in our_puuids:
                loc = k.get("victim_death_location") or {}
                if loc.get("x") is not None and loc.get("y") is not None:
                    normalized = normalize_location(loc["x"], loc["y"], map_uuid=map_uuid)
                    if normalized:
                        locations.append({**normalized, "puuid": puuid})
    return locations


def _upsert_summary_row(
    db: Session, team_id: str, stat_type: str, dimension_key: str, wins: int, losses: int, metrics: dict
) -> None:
    """(team_id, stat_type, dimension_key) 한 행을 원자적으로 upsert한다.

    2026-09-11 실측 확인: 기존에는 "조회 후 없으면 add"(TOCTOU) 방식이라, 이 팀의
    "팀 분석"/"AI 리포트" 탭을 거의 동시에 두 번 조회하면(우리팀 분석 페이지가
    stats/analysis를 병렬로 불러오는 것처럼) 두 세션이 동시에 "없음"을 보고 동시에
    INSERT를 시도해 uq_team_stats 중복 키 IntegrityError가 실제로 발생했다
    (services/team_engagement_cache.py::upsert_match_engagement가 2026-09-08에
    겪었던 것과 같은 종류의 경합). MySQL 네이티브 INSERT ... ON DUPLICATE KEY UPDATE로
    바꿔 그 경합 자체를 없앤다."""
    stmt = mysql_insert(TeamStatsSummary).values(
        team_id=team_id, stat_type=stat_type, dimension_key=dimension_key,
        wins=wins, losses=losses, metrics_json=metrics,
    )
    stmt = stmt.on_duplicate_key_update(
        wins=stmt.inserted.wins, losses=stmt.inserted.losses, metrics_json=stmt.inserted.metrics_json,
    )
    db.execute(stmt)


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

        our_color = determine_team_color(rounds, our_puuids)
        if our_color is None:
            continue  # 방어적 스킵 - 이 매치는 공수/승패 판정 불가

        records = analyze_rounds(rounds, our_color)
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
            "combos": [], "players": {},
            "death_locations": [],
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

        # 우리 로스터 사망 좌표 - 맵별로 누적해 히트맵 데이터로 쓴다. _death_locations_for_match 참고.
        bucket["death_locations"].extend(_death_locations_for_match(rounds, our_puuids, match.map_uuid))

        agent_names = [
            (agents["by_uuid"].get((r.agent_uuid or "").lower()) or {}).get("name_ko") or "-"
            for r in our_rows
        ]
        if len(agent_names) == 5:
            bucket["combos"].append({"agents": agent_names, "result": result})

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
    round_phase_metrics, overall_wins, overall_losses = aggregate_round_phase(all_records)
    _upsert_summary_row(db, team_id, "round_phase", "overall", overall_wins, overall_losses, round_phase_metrics)

    # --- ③ 교전 정보 캐싱 ---
    our_duelist_avg = sum(our_duelist_acs) / len(our_duelist_acs) if our_duelist_acs else 0.0
    opp_duelist_avg = sum(opp_duelist_acs) / len(opp_duelist_acs) if opp_duelist_acs else 0.0
    matchup = _duelist_matchup_from_acs(our_duelist_avg, opp_duelist_avg)
    engagement_metrics = {
        "trade1v1": pct(clutch_totals[1]["win"], clutch_totals[1]["loss"]),
        "trade1v2": pct(clutch_totals[2]["win"], clutch_totals[2]["loss"]),
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

        # 요원 조합: 맵당 표본이 보통 1~2경기뿐이라 승률로 집계하면 0%/100%만 나와 의미가 없다.
        # 조합을 묶지 않고 실제 치른 경기(최신순, matches와 동일한 정렬)를 그대로 한 줄씩 노출한다.
        game_combos = b["combos"]

        player_summaries = []
        for puuid, pb in b["players"].items():
            avg_acs = round(pb["acs_sum"] / pb["acs_n"]) if pb["acs_n"] else 0
            fd_rate = round(pb["fd_sum"] / pb["rounds_sum"] * 100) if pb["rounds_sum"] else 0
            player_summaries.append({"name": riot_names.get(puuid, "-"), "acs": avg_acs, "fd": fd_rate})

        best = max(player_summaries, key=lambda p: p["acs"], default=None)
        worst = max(player_summaries, key=lambda p: p["fd"], default=None)

        # 팀원 사망 위치 분석(히트맵) - 로스터 5명 기준으로 선수당 대표 위치 1개씩만 뽑는다.
        # compute_player_hotspots는 puuid만 알고 이름은 몰라 여기서 riot_names(위에서
        # 이미 조회됨)로 이름을 붙인다.
        death_hotspots = compute_player_hotspots(b["death_locations"])
        for h in death_hotspots:
            h["playerName"] = riot_names.get(h["playerId"], "-")

        metrics = {
            "mapName": map_names.get(map_uuid_key, "-"),
            "mapWinRate": pct(b["win"], b["lose"]),
            "atkWinRate": pct(b["atk_w"], b["atk_l"]),
            "defWinRate": pct(b["def_w"], b["def_l"]),
            "preferredSite": preferred_site,
            "avgSpikePlantTime": avg_plant_sec,
            "matchSample": games,
            "combos": game_combos,
            "comboAce": [{"name": best["name"], "acs": best["acs"]}] if best else [],
            "comboWeakness": [{"name": worst["name"], "fd": worst["fd"], "acs": worst["acs"]}] if worst else [],
            # 팀원 사망 위치 분석(히트맵) 섹션용 - 선수당 1개(최대 5개). _death_locations_for_match 참고.
            "deathLocations": death_hotspots,
        }
        _upsert_summary_row(db, team_id, "map_side", map_uuid_key, b["win"], b["lose"], metrics)

    db.commit()


def build_my_team_analysis(db: Session, team_id: str) -> dict:
    """캐시(team_stats_summary)가 있으면 그대로 읽고, 없으면(첫 진입) 계산해서 채운 뒤
    읽는다.

    _compute_and_cache는 한 팀당 여러 행(round_phase/engagement/맵별)을 한 트랜잭션
    안에서 upsert한다 - _upsert_summary_row가 원자적 upsert로 바뀌어(위 함수 참고)
    중복 키 에러는 없어졌지만, 같은 팀을 거의 동시에 두 세션이 계산하면(예: "팀 분석"
    탭과 "AI 리포트" 탭이 동시에 이 팀을 처음 조회) 여러 행에 걸친 잠금 순서 차이로
    데드락(OperationalError 1213)이 날 수 있다(실측 재현 확인). 데드락이든 그 사이
    다른 세션이 먼저 채워서 생기는 나머지 충돌이든, 롤백 후 캐시를 다시 읽어보면 대부분
    이미 채워져 있어 재계산 없이 바로 해결된다 - 그래도 비어있으면 한 번 더 계산을
    시도한다(진짜 일시적 데드락이었던 경우)."""
    rows = db.query(TeamStatsSummary).filter(TeamStatsSummary.team_id == team_id).all()
    if not rows:
        for attempt in range(2):
            try:
                _compute_and_cache(db, team_id)
                break
            except (IntegrityError, OperationalError):
                db.rollback()
                rows = db.query(TeamStatsSummary).filter(TeamStatsSummary.team_id == team_id).all()
                if rows or attempt == 1:
                    break
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