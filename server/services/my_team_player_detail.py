"""
로그인한 팀 전용 "우리팀 분석 > 개인 분석 > 선수 상세" 페이지 데이터 조립 +
player_stats_summary 캐싱.

services/my_team_analysis.py(팀 분석 탭)와 같은 전제 - Henrik을 실시간으로 부르지 않고
matches.round_detail_json/match_player_stats만으로 계산한다(2026-09-10 사용자 확인:
player_stats_summary가 채워지지 않은 선수(=이 페이지 첫 방문)에 한해 계산 후 캐싱하는
cache-aside, 이후 조회는 캐시만 읽음. 나중에 "갱신" 버튼이 생기면 그때 재계산 트리거를
추가하면 됨 - 지금은 신경쓰지 않는다).

라운드 단위 파생값은 my_team_analysis.py와 최대한 같은 정의를 재사용한다(공격/수비 구간,
피스톨, Eco, 클러치 판정 등 - _determine_our_color/_round_segments/_segment_attackers/
_round_kill_events/ECO_THRESHOLD를 그대로 가져다 쓴다). 다만 팀 분석은 "라운드 승/패"를
집계하는 반면 여기는 "이 선수의 K/D·ACS"를 라운드 상황별로 집계한다는 점이 다르다.

2026-09-10 사용자 확인 후 진행하기로 한 부분(이 페이지에서만 새로 필요했던 정의 - 문서화):
  - 무기별 K/D: 그 무기로 낸 킬 수 / 그 무기를 들고 있다가 죽은 라운드 수(죽은 적이 없으면
    킬 수 그대로). 무기별 ADR: 그 무기를 들고 있던 라운드들의 평균 데미지.
  - 개인 클러치(1v1/1v2/1v3+): 라운드마다 우리 팀에서 "이 선수"가 마지막 생존자가 된
    순간 상대가 몇 명 남아있었는지로 분류(다른 선수가 마지막 생존자면 이 선수의 클러치
    시도로 안 침). 3명 이상은 1v3plus로 합산.
  - 트레이드 1v1/1v2: 이 선수가 죽은 시점에 상대가 몇 명 살아있었는지로 상황을 나누고
    (1명=1v1, 2명=1v2, 3명 이상은 집계 제외), match_sync.py와 같은 TRADE_WINDOW_MS(5초)
    안에 그 킬러가 처치됐는지로 성공/실패를 센다.
  - 스킬 사용 유효율: Henrik의 ability_casts가 항상 null이라(팀 분석 때 이미 확인됨)
    데이터 소스가 없어 항상 빈 배열로 둔다.
  - 교전 거리 분포: kill_events의 좌표는 실제 미터 단위가 아니라 게임 내 임의 좌표계라,
    100으로 나눈 값을 "대략적인 미터"로 근사한다(정확한 맵별 스케일 정보가 코드베이스에
    없음 - 절대값의 정확성은 보장하지 않는, 상대적 분포 참고용).
"""
import json as json_module
import math
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, defer

from ml.engagement_predictor import _duelist_matchup_from_acs
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.player_stats_summary import PlayerStatsSummary
from models.riot_account import RiotAccount
from services.my_team_analysis import (
    ECO_THRESHOLD,
    _determine_our_color,
    _round_kill_events,
    _round_segments,
    _segment_attackers,
)
from services.my_team_stats import MATCH_HISTORY_LIMIT, _load_map_name_by_uuid

# match_sync.py::TRADE_WINDOW_MS와 같은 값(5초) - 죽은 뒤 이 시간 안에 킬러가 처치되면
# "트레이드 성공"으로 본다. 스키마가 같은 round_detail_json을 쓰므로 여기선 그대로 재사용.
TRADE_WINDOW_MS = 5000

# 무기 목록은 킬 수 기준 상위 이만큼만 캐싱(화면이 무한 스크롤 리스트가 아니라 카드 나열이라
# 너무 많으면 의미 없음 - 나중에 필요하면 조정).
MAX_WEAPONS = 5

_HITZONE_ORDER = ["헤드", "바디", "레그"]

_ref_weapons_cache: dict | None = None


def _load_ref_weapons(db: Session) -> dict:
    """ref_weapons.uuid(소문자) -> 영문 무기명. front/src/constants/gameData.js의
    weapons[].id가 이 영문 소문자 포맷과 동일하다."""
    global _ref_weapons_cache
    if _ref_weapons_cache is not None:
        return _ref_weapons_cache
    rows = db.execute(text("SELECT uuid, display_name FROM ref_weapons")).mappings().all()
    _ref_weapons_cache = {r["uuid"].lower(): r["display_name"] for r in rows}
    return _ref_weapons_cache


def _pct(wins: int, losses: int) -> int:
    total = wins + losses
    return round(wins / total * 100) if total else 0


def _aggregate_player_round_phase(records: list[dict]) -> dict:
    """공격/수비/피스톨/Eco 구간별 이 선수의 K/D·ACS, 전체 라운드 기준 FB·FD 비율."""

    def _bucket(pred) -> tuple[float, int]:
        kills = deaths = 0
        scores = []
        for r in records:
            if not pred(r):
                continue
            kills += r["kills"]
            deaths += 1 if r["died"] else 0
            scores.append(r["score"])
        kd = round(kills / deaths, 2) if deaths else float(kills)
        acs = round(sum(scores) / len(scores)) if scores else 0
        return kd, acs

    atk_kd, atk_acs = _bucket(lambda r: r["we_attacked"] is True)
    def_kd, def_acs = _bucket(lambda r: r["we_attacked"] is False)
    pistol_kd, pistol_acs = _bucket(lambda r: r["is_pistol"])
    eco_kd, eco_acs = _bucket(lambda r: r["is_eco"] is True)

    total = len(records)
    fb_rounds = sum(1 for r in records if r["got_fb"])
    fd_rounds = sum(1 for r in records if r["got_fd"])

    return {
        "atkKd": atk_kd, "atkAcs": atk_acs,
        "defKd": def_kd, "defAcs": def_acs,
        "fbPct": round(fb_rounds / total * 100) if total else 0,
        "fdPct": round(fd_rounds / total * 100) if total else 0,
        "pistolKd": pistol_kd, "pistolAcs": pistol_acs,
        "ecoKd": eco_kd, "ecoAcs": eco_acs,
    }


def _upsert_summary_row(db: Session, puuid: str, stat_type: str, dimension_key: str, metrics: dict) -> None:
    row = (
        db.query(PlayerStatsSummary)
        .filter(
            PlayerStatsSummary.puuid == puuid,
            PlayerStatsSummary.stat_type == stat_type,
            PlayerStatsSummary.dimension_key == dimension_key,
        )
        .first()
    )
    if row is None:
        row = PlayerStatsSummary(puuid=puuid, stat_type=stat_type, dimension_key=dimension_key)
        db.add(row)
    row.metrics_json = metrics


def _kill_weapon_uuid(kill_event: dict, fallback_uuid: str | None) -> str | None:
    weapon_uuid = kill_event.get("damage_weapon_id")
    return weapon_uuid.lower() if weapon_uuid else fallback_uuid


def _compute_and_cache(db: Session, team_id: str, puuid: str) -> None:
    base_query = (
        db.query(Match)
        .join(MatchPlayerStat, MatchPlayerStat.match_id == Match.match_id)
        .filter(MatchPlayerStat.puuid == puuid, MatchPlayerStat.team_id == team_id)
        .options(defer(Match.round_detail_json))
    )
    matches = sorted(base_query.all(), key=lambda m: m.game_start or datetime.min, reverse=True)[
        :MATCH_HISTORY_LIMIT
    ]
    match_ids = [m.match_id for m in matches]
    if not match_ids:
        return

    detail_by_id: dict[str, list] = {}
    stmt = text("SELECT match_id, round_detail_json FROM matches WHERE match_id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    for r in db.execute(stmt, {"ids": match_ids}).mappings().all():
        raw = r["round_detail_json"]
        parsed = json_module.loads(raw) if isinstance(raw, str) else raw
        detail_by_id[r["match_id"]] = parsed if isinstance(parsed, list) else []

    all_stats_rows = db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id.in_(match_ids)).all()
    by_match: dict[str, list[MatchPlayerStat]] = {}
    for s in all_stats_rows:
        by_match.setdefault(s.match_id, []).append(s)

    map_names = _load_map_name_by_uuid(db)
    weapon_names = _load_ref_weapons(db)

    all_records: list[dict] = []
    map_records: dict[str, list[dict]] = {}
    map_name_by_key: dict[str, str] = {}

    heads = bodies = legs = 0
    weapon_kills: dict[str, int] = {}
    weapon_deaths: dict[str, int] = {}
    weapon_damage: dict[str, int] = {}
    weapon_rounds: dict[str, int] = {}

    clutch_tally = {1: {"win": 0, "loss": 0}, 2: {"win": 0, "loss": 0}, 3: {"win": 0, "loss": 0}}
    trade_tally = {1: {"win": 0, "loss": 0}, 2: {"win": 0, "loss": 0}}

    distance_buckets = {"0-5m": 0, "5-10m": 0, "10-15m": 0, "15-20m": 0, "20m+": 0}
    distance_total = 0

    target_acs_values: list[int] = []
    opp_role_acs_values: list[int] = []
    target_role_counts: dict[str, int] = {}

    for match in matches:
        rounds = detail_by_id.get(match.match_id)
        if not rounds:
            continue
        roster = by_match.get(match.match_id) or []
        our_rows = [r for r in roster if r.team_id == team_id]
        opp_rows = [r for r in roster if r.team_id != team_id]
        our_puuids = {r.puuid for r in our_rows}
        opp_puuids = {r.puuid for r in opp_rows}

        our_color = _determine_our_color(rounds, our_puuids)
        if our_color is None:
            continue

        target_row = next((r for r in our_rows if r.puuid == puuid), None)
        if target_row is not None:
            if target_row.acs is not None:
                target_acs_values.append(target_row.acs)
            if target_row.role_type:
                target_role_counts[target_row.role_type] = target_role_counts.get(target_row.role_type, 0) + 1

        map_key = (match.map_uuid or "").lower()
        map_name_by_key[map_key] = map_names.get(map_key, "-")

        segments = _round_segments(len(rounds))
        attackers = _segment_attackers(rounds, segments)

        for i, rnd in enumerate(rounds):
            ps_list = rnd.get("player_stats") or []
            ps_target = next((ps for ps in ps_list if ps.get("player_puuid") == puuid), None)
            if ps_target is None:
                continue  # 그 라운드에 이 선수 데이터가 없음(방어적 스킵 - 대타 교체 등)

            seg = next(s for s in segments if s[0] <= i < s[1])
            attacker = attackers[seg]
            we_attacked = None if attacker is None else (attacker == our_color)

            kills_merged = _round_kill_events(rnd)
            died_this_round = any(k.get("victim_puuid") == puuid for k in kills_merged)
            opening = kills_merged[0] if kills_merged else None
            got_fb = bool(opening and opening.get("killer_puuid") == puuid)
            got_fd = bool(opening and opening.get("victim_puuid") == puuid)

            our_loadouts = [
                (ps.get("economy") or {}).get("loadout_value")
                for ps in ps_list
                if ps.get("player_team") == our_color and (ps.get("economy") or {}).get("loadout_value") is not None
            ]
            is_eco = (sum(our_loadouts) / len(our_loadouts) < ECO_THRESHOLD) if our_loadouts else None

            record = {
                "we_attacked": we_attacked,
                "is_pistol": i in (0, 12),
                "is_eco": is_eco,
                "score": ps_target.get("score") or 0,
                "kills": ps_target.get("kills") or 0,
                "died": died_this_round,
                "got_fb": got_fb,
                "got_fd": got_fd,
            }
            all_records.append(record)
            map_records.setdefault(map_key, []).append(record)

            # --- 히트박스(부위별 타격) ---
            heads += ps_target.get("headshots") or 0
            bodies += ps_target.get("bodyshots") or 0
            legs += ps_target.get("legshots") or 0

            # --- 무기별 K/D·ADR ---
            equipped = ((ps_target.get("economy") or {}).get("weapon") or {}).get("id")
            equipped = equipped.lower() if equipped else None
            if equipped:
                weapon_damage[equipped] = weapon_damage.get(equipped, 0) + (ps_target.get("damage") or 0)
                weapon_rounds[equipped] = weapon_rounds.get(equipped, 0) + 1
                if died_this_round:
                    weapon_deaths[equipped] = weapon_deaths.get(equipped, 0) + 1
            for ke in ps_target.get("kill_events") or []:
                wpn = _kill_weapon_uuid(ke, equipped)
                # damage_weapon_id가 항상 총 UUID인 건 아니다 - 어빌리티로 처치한 킬은
                # 해당 스킬의 UUID가 들어와서 ref_weapons에 없다(match_sync.py:371의
                # weapon_uuids 검증과 동일한 이유). ref_weapons에 있는 진짜 무기만 집계.
                if wpn and wpn in weapon_names:
                    weapon_kills[wpn] = weapon_kills.get(wpn, 0) + 1

            # --- 개인 클러치: 우리 팀에서 이 선수가 마지막 생존자가 된 순간 ---
            our_alive = set(our_puuids)
            opp_alive = set(opp_puuids)
            clutch_n = None
            for k in kills_merged:
                victim = k.get("victim_puuid")
                our_alive.discard(victim)
                opp_alive.discard(victim)
                if clutch_n is None and len(our_alive) == 1 and puuid in our_alive and len(opp_alive) >= 1:
                    clutch_n = len(opp_alive)
            if clutch_n is not None:
                bucket = clutch_n if clutch_n in (1, 2) else 3
                won = rnd.get("winning_team") == our_color
                clutch_tally[bucket]["win" if won else "loss"] += 1

            # --- 트레이드: 이 선수가 죽은 시점 상대 생존자 수 기준 1v1/1v2 ---
            if died_this_round:
                my_death = next(k for k in kills_merged if k.get("victim_puuid") == puuid)
                alive_our, alive_opp = set(our_puuids), set(opp_puuids)
                for k in kills_merged:
                    if k is my_death:
                        break
                    alive_our.discard(k.get("victim_puuid"))
                    alive_opp.discard(k.get("victim_puuid"))
                opp_alive_at_death = len(alive_opp)
                if opp_alive_at_death in (1, 2):
                    killer = my_death.get("killer_puuid")
                    death_time = my_death.get("kill_time_in_round") or 0
                    traded = any(
                        k.get("victim_puuid") == killer
                        and 0 <= ((k.get("kill_time_in_round") or 0) - death_time) <= TRADE_WINDOW_MS
                        for k in kills_merged
                    )
                    trade_tally[opp_alive_at_death]["win" if traded else "loss"] += 1

            # --- 교전 거리(근사) : 이 선수가 낸 킬의 킬러-피격자 좌표 거리 ---
            for ke in ps_target.get("kill_events") or []:
                victim_loc = ke.get("victim_death_location") or {}
                killer_loc = next(
                    (
                        pl.get("location")
                        for pl in ke.get("player_locations_on_kill") or []
                        if pl.get("player_puuid") == puuid
                    ),
                    None,
                )
                if not killer_loc or "x" not in victim_loc:
                    continue
                dx = (killer_loc.get("x") or 0) - (victim_loc.get("x") or 0)
                dy = (killer_loc.get("y") or 0) - (victim_loc.get("y") or 0)
                approx_m = math.hypot(dx, dy) / 100  # 실제 미터 스케일 아님 - 모듈 docstring 참고
                distance_total += 1
                if approx_m < 5:
                    distance_buckets["0-5m"] += 1
                elif approx_m < 10:
                    distance_buckets["5-10m"] += 1
                elif approx_m < 15:
                    distance_buckets["10-15m"] += 1
                elif approx_m < 20:
                    distance_buckets["15-20m"] += 1
                else:
                    distance_buckets["20m+"] += 1

        # --- 역할 매치업용 상대팀 ACS(이 선수와 같은 포지션) ---
        target_role = target_row.role_type if target_row else None
        if target_role:
            for r in opp_rows:
                if r.role_type == target_role and r.acs is not None:
                    opp_role_acs_values.append(r.acs)

    if not all_records:
        return  # 방어적 스킵 - round_detail_json이 하나도 없어 계산 불가

    # --- ① 라운드 정보 캐싱 (전체 맵 + 맵별) ---
    _upsert_summary_row(db, puuid, "round_phase", "overall", _aggregate_player_round_phase(all_records))
    for map_key, records in map_records.items():
        if not map_key or not records:
            continue
        metrics = _aggregate_player_round_phase(records)
        metrics["mapName"] = map_name_by_key.get(map_key, "-")
        _upsert_summary_row(db, puuid, "round_phase", map_key, metrics)

    # --- ② 히트박스(타격 비율) 캐싱 ---
    total_shots = heads + bodies + legs
    zone_pcts = {
        "헤드": round(heads / total_shots * 100) if total_shots else 0,
        "바디": round(bodies / total_shots * 100) if total_shots else 0,
        "레그": round(legs / total_shots * 100) if total_shots else 0,
    }
    for zone, pct in zone_pcts.items():
        _upsert_summary_row(db, puuid, "hitbox", zone, {"pct": pct})

    # --- ③ 무기별 K/D·ADR 캐싱 (킬 수 상위 MAX_WEAPONS개) ---
    top_weapons = sorted(weapon_kills, key=weapon_kills.get, reverse=True)[:MAX_WEAPONS]
    for wpn in top_weapons:
        kills = weapon_kills.get(wpn, 0)
        deaths = weapon_deaths.get(wpn, 0)
        rounds_used = weapon_rounds.get(wpn, 0)
        kd = round(kills / deaths, 2) if deaths else float(kills)
        adr = round(weapon_damage.get(wpn, 0) / rounds_used) if rounds_used else 0
        _upsert_summary_row(
            db, puuid, "weapon", wpn,
            {"name": weapon_names.get(wpn, wpn), "kd": kd, "adr": adr},
        )

    # --- ④ 클러치 캐싱 ---
    clutch_keys = {1: "1v1", 2: "1v2", 3: "1v3plus"}
    for n, key in clutch_keys.items():
        _upsert_summary_row(
            db, puuid, "clutch", key,
            {"successRate": _pct(clutch_tally[n]["win"], clutch_tally[n]["loss"])},
        )

    # --- ⑤ 트레이드 캐싱 ---
    _upsert_summary_row(
        db, puuid, "engagement", "trade",
        {
            "trade1v1": _pct(trade_tally[1]["win"], trade_tally[1]["loss"]),
            "trade1v2": _pct(trade_tally[2]["win"], trade_tally[2]["loss"]),
        },
    )

    # --- ⑥ 스킬 사용 유효율 : 데이터 소스 없음(모듈 docstring 참고) - 항상 빈 배열 ---
    _upsert_summary_row(db, puuid, "engagement", "skills", {"skills": []})

    # --- ⑦ 교전 거리 분포(근사) ---
    distance_distribution = [
        {"x": label, "y": round(count / distance_total * 100) if distance_total else 0}
        for label, count in distance_buckets.items()
    ]
    _upsert_summary_row(db, puuid, "engagement", "distanceDistribution", {"distanceDistribution": distance_distribution})

    # --- ⑧ 포지션별 상대 비교(역할 매치업) ---
    target_role = max(target_role_counts, key=target_role_counts.get) if target_role_counts else None
    target_avg = sum(target_acs_values) / len(target_acs_values) if target_acs_values else 0.0
    opp_avg = sum(opp_role_acs_values) / len(opp_role_acs_values) if opp_role_acs_values else 0.0
    matchup = _duelist_matchup_from_acs(target_avg, opp_avg)
    _upsert_summary_row(
        db, puuid, "role_matchup", target_role or "overall",
        {"me": matchup["ourScore"], "opponent": matchup["theirScore"]},
    )

    db.commit()


def build_my_team_player_detail(db: Session, team_id: str, puuid: str) -> dict | None:
    """캐시(player_stats_summary)가 있으면 그대로 읽고, 없으면(첫 진입) 계산해서 채운 뒤
    읽는다. puuid가 이 팀 로스터가 아니면 None(라우터에서 404로 변환)."""
    is_our_roster = (
        db.query(MatchPlayerStat)
        .filter(MatchPlayerStat.puuid == puuid, MatchPlayerStat.team_id == team_id)
        .first()
        is not None
    )
    if not is_our_roster:
        return None

    account = db.get(RiotAccount, puuid)
    if account is None:
        return None

    rows = db.query(PlayerStatsSummary).filter(PlayerStatsSummary.puuid == puuid).all()
    if not rows:
        _compute_and_cache(db, team_id, puuid)
        rows = db.query(PlayerStatsSummary).filter(PlayerStatsSummary.puuid == puuid).all()

    round_info_by_map: dict = {}
    hitzone_by_zone: dict = {}
    weapons: list = []
    clutch: dict = {}
    trade1v1 = trade1v2 = 0
    skills: list = []
    distance_distribution: list = []
    duelist_compare = {"me": 0, "opponent": 0}

    for row in rows:
        metrics = row.metrics_json or {}
        if row.stat_type == "round_phase":
            if row.dimension_key == "overall":
                round_info_by_map["전체 맵"] = metrics
            else:
                metrics = dict(metrics)
                map_name = metrics.pop("mapName", row.dimension_key)
                round_info_by_map[map_name] = metrics
        elif row.stat_type == "hitbox":
            hitzone_by_zone[row.dimension_key] = metrics.get("pct", 0)
        elif row.stat_type == "weapon":
            weapons.append({"name": metrics.get("name", row.dimension_key), "kd": metrics.get("kd", 0), "adr": metrics.get("adr", 0)})
        elif row.stat_type == "clutch":
            clutch[row.dimension_key] = metrics.get("successRate", 0)
        elif row.stat_type == "role_matchup":
            duelist_compare = {"me": metrics.get("me", 0), "opponent": metrics.get("opponent", 0)}
        elif row.stat_type == "engagement":
            if row.dimension_key == "trade":
                trade1v1 = metrics.get("trade1v1", 0)
                trade1v2 = metrics.get("trade1v2", 0)
            elif row.dimension_key == "skills":
                skills = metrics.get("skills", [])
            elif row.dimension_key == "distanceDistribution":
                distance_distribution = metrics.get("distanceDistribution", [])

    weapons.sort(key=lambda w: w["kd"], reverse=True)

    return {
        "id": puuid,
        "name": account.riot_name,
        "tag": account.riot_tag,
        "avatarUrl": account.avatar_url,
        "level": account.account_level,
        "title": account.title,
        "roundInfoByMap": round_info_by_map,
        "aim": {
            "hitzones": [{"zone": z, "pct": hitzone_by_zone.get(z, 0)} for z in _HITZONE_ORDER],
            "weapons": weapons,
            "clutch": {
                "1v1": clutch.get("1v1", 0),
                "1v2": clutch.get("1v2", 0),
                "1v3plus": clutch.get("1v3plus", 0),
            },
        },
        "engagement": {
            "trade1v1": trade1v1,
            "trade1v2": trade1v2,
            "skills": skills,
            "duelistCompare": duelist_compare,
            "distanceDistribution": distance_distribution,
        },
    }
