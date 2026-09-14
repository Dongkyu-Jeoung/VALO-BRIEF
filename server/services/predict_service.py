"""
승부 예측(routers/predict.py) 지원 서비스.
- resolve_recent_roster: team_name/team_tag의 최근 매치에서 5인 로스터(name/tag)를 찾는다.
  teams 테이블엔 로스터 매핑이 없어서(팀 대표를 개인 계정 단위로 묶지 않기로 한 결정,
  services/team_profile.py와 동일 전제) 예측할 때마다 Henrik 매치 이력에서 다시 뽑아야 한다.
- save_prediction: 예측 결과 1건을 predictions 테이블에 저장.
- load_premier_prediction_features: 양 팀의 Premier 경기만으로 선수 피처를 집계한다.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from math import isfinite

from sqlalchemy.orm import Session

from models.prediction import Prediction
from models.team import Team
from services import henrik_api

_KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    """predictions.created_at을 KST로 명시적으로 채운다 - 컬럼의 DB 기본값
    (server_default=func.now())은 RDS 서버 자체 시간대(기본 UTC)를 따라서 그대로 두면
    실제 한국 시간보다 9시간 늦게 찍힌다(services/match_sync.py 등의 동일 패턴 참고)."""
    return datetime.now(_KST).replace(tzinfo=None)

# 이력에서 가장 최근 매치부터 몇 건까지 살펴보며 5인 로스터가 온전히 잡히는 매치를 찾을지.
# services/team_profile.py의 MATCH_HISTORY_LIMIT(10)보다 훨씬 적게 잡았다 - 로스터 5명만
# 있으면 바로 멈추므로 대부분 첫 매치에서 끝나고, 여러 건을 동시에 불러올 필요도 없다.
ROSTER_LOOKUP_LIMIT = 5

logger = logging.getLogger(__name__)
MIN_PREMIER_MATCHES = 3
INCOMPLETE_PREMIER_MESSAGE = "Premier 경기 상세 데이터가 불완전하여 예측에 사용할 수 있는 경기가 3개 미만입니다."
INSUFFICIENT_PREMIER_MESSAGE = (
    "최근 Premier 경기 데이터가 부족하여 승부예측을 진행할 수 없습니다. "
    "최소 3경기의 Premier 경기 기록이 필요합니다."
)


async def get_recent_premier_match_ids(team_name, team_tag):
    """History의 유효한 경기 ID를 날짜순으로 정렬하고 중복 제거 후 최대 5개 선택."""
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    if not isinstance(history, dict):
        logger.warning("[PREMIER REJECT] team=%s#%s reason=HISTORY_INVALID type=%s", team_name, team_tag, type(history).__name__)
        raise ValueError(INSUFFICIENT_PREMIER_MESSAGE)
    matches = []
    for entry in (history or {}).get("league_matches") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            logger.warning("[PREMIER HISTORY SKIP] team=%s#%s reason=INVALID_MATCH_ID", team_name, team_tag)
            continue
        try:
            started = datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.warning("[PREMIER HISTORY SKIP] team=%s#%s match=%s reason=INVALID_DATE value=%r", team_name, team_tag, entry["id"], entry.get("started_at"))
            continue
        if started <= datetime.now(timezone.utc):
            matches.append((started, entry["id"]))
        else:
            logger.warning("[PREMIER HISTORY SKIP] team=%s#%s match=%s reason=FUTURE_DATE value=%s", team_name, team_tag, entry["id"], started)
    ids = list(dict.fromkeys(mid for _, mid in sorted(matches, reverse=True)))[:5]
    logger.debug("[PREMIER HISTORY] team=%s#%s matches_found=%d", team_name, team_tag, len(ids))
    if len(ids) < MIN_PREMIER_MATCHES:
        logger.warning("[PREMIER REJECT] team=%s#%s reason=HISTORY_TOO_SHORT raw=%d valid=%d unique_selected=%d ids=%s", team_name, team_tag, len(history.get("league_matches") or []), len(matches), len(ids), ids)
        raise ValueError(INSUFFICIENT_PREMIER_MESSAGE)
    return ids


def _premier_player_rows(detail, team_name, team_tag, match_id=None, diagnostic=None):
    """v2 상세에서 해당 Premier 로스터의 완전한 5인 기록만 추출한다."""
    from services.match_sync import calculate_match_kast, _match_our_side

    def reject(reason):
        if diagnostic is not None:
            diagnostic["reason"] = reason
        logger.warning("[PREMIER MATCH REJECT] team=%s#%s match=%s reason=%s", team_name, team_tag, match_id, reason)
        return []

    if not isinstance(detail, dict):
        return reject(f"DETAIL_INVALID type={type(detail).__name__}")
    stage = "TEAM_LOOKUP"
    player_id = None
    try:
        match_id = match_id or (detail.get("metadata") or {}).get("matchid") or "unknown"
        side = _match_our_side(detail, team_name, team_tag)
        if side is None:
            rosters = {s: {k: ((detail.get("teams") or {}).get(s, {}).get("roster") or {}).get(k) for k in ("name", "tag")} for s in ("red", "blue")}
            return reject(f"TEAM_NOT_FOUND rosters={rosters}")
        teams = detail["teams"]
        stage = "ROSTER_SELECTION"
        members = set(teams[side]["roster"]["members"])
        players = detail["players"]["all_players"]
        selected = [p for p in players if p.get("puuid") in members and str(p.get("team", "")).lower() == side]
        if len(players) != 10 or len(selected) != 5 or len({p["puuid"] for p in selected}) != 5:
            return reject(f"ROSTER_INVALID total={len(players)} selected={len(selected)} members={len(members)} missing_members={sorted(members - {p.get('puuid') for p in players})} players={[(p.get('puuid'), p.get('team')) for p in players]}")
        stage = "KAST"
        kast_reasons = []
        # 출력만 제어한다. 오류 사유 수집 콜백은 항상 유지한다.
        kast_logging_enabled = os.getenv("PREMIER_KAST_DEBUG", "false").strip().lower() in (
            "true", "1", "yes", "on",
        )
        def report_kast(reason):
            if not reason.startswith(("EVENT_DETAIL", "SPECIAL_EVENTS_NORMALIZED")):
                kast_reasons.append(reason)
            if kast_logging_enabled:
                logger.warning("[PREMIER KAST] team=%s#%s match=%s %s", team_name, team_tag, match_id, reason)
        kast = calculate_match_kast(detail, report=report_kast, reconcile_special=True)
        if not kast:
            return reject("KAST_INVALID " + (kast_reasons[-1] if kast_reasons else "EMPTY_KAST"))
        stage = "RESULT"
        rounds = len(detail["rounds"])
        won = teams[side]["has_won"]
        if not isinstance(won, bool) or not rounds:
            return reject(f"RESULT_INVALID has_won={won!r} rounds={rounds}")
        rows = []
        for p in selected:
            stage = "PLAYER_STATS"
            player_id = p.get("puuid")
            stats = p["stats"]
            required = ("score", "kills", "deaths", "headshots", "bodyshots", "legshots")
            if any(not isinstance(stats.get(k), (int, float)) or not isfinite(stats[k]) or stats[k] < 0 for k in required):
                return reject(f"STATS_INVALID puuid={p.get('puuid')} values={ {k: stats.get(k) for k in required} }")
            shots = sum(stats[k] for k in ("headshots", "bodyshots", "legshots"))
            rows.append({
                "puuid": p["puuid"], "agent": p["character"],
                "acs": round(stats["score"] / rounds, 1),
                "kd": round(stats["kills"] / max(1, stats["deaths"]), 2),
                "kast": kast[p["puuid"]],
                "headshot_pct": round(stats["headshots"] / shots * 100, 1) if shots else 0.0,
                "win": int(won),
            })
        from ml.rolling import aggregate_player_rows
        for row in rows:
            stage = "PLAYER_FEATURE_VALIDATION"
            player_id = row["puuid"]
            aggregate_player_rows([row], row["puuid"])
        return rows
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return reject(f"PARSE_OR_FEATURE_INVALID stage={stage} puuid={player_id} {type(exc).__name__}: {exc}")


def build_premier_player_features(details, team_name, team_tag, match_ids=None):
    """Average all five appearances per valid match; slots are not player identities."""
    from ml.team_feature import validate_player_feature

    games = []
    diagnostics = []
    for index, detail in enumerate(details[:5]):
        mid = match_ids[index] if match_ids else ((detail.get("metadata") or {}).get("matchid") if isinstance(detail, dict) else None)
        diagnostic = {"match": mid or f"slot-{index + 1}", "status": "REJECTED"}
        rows = _premier_player_rows(detail, team_name, team_tag, mid, diagnostic)
        if rows:
            games.append(rows)
            diagnostic["status"] = "ACCEPTED"
        diagnostics.append(diagnostic)
    logger.warning("[PREMIER VALIDATION SUMMARY] team=%s#%s selected=%d valid=%d rejected=%d matches=%s", team_name, team_tag, len(diagnostics), len(games), len(diagnostics) - len(games), diagnostics)
    if len(games) < MIN_PREMIER_MATCHES:
        logger.warning("[PREMIER REJECT] team=%s#%s reason=VALID_MATCHES_TOO_SHORT selected=%d valid=%d", team_name, team_tag, len(details[:5]), len(games))
        raise ValueError(INCOMPLETE_PREMIER_MESSAGE)
    mapping = {"acs": "recent_acs", "kd": "recent_kd", "kast": "recent_kast",
               "headshot_pct": "recent_headshot_pct", "win": "recent_winrate"}
    means = {feature: round(sum(row[col] for game in games for row in game) / (5 * len(games)), 2)
             for col, feature in mapping.items()}
    # Keep the existing five-feature input contract and latest agent composition.
    # These are team-average slots, NOT histories attributed to individual PUUIDs.
    features = [{"agent": row["agent"], **means} for row in games[0]]
    for feature in features:
        validate_player_feature(feature)
    logger.debug("[PREMIER TEAM AVERAGE] team=%s#%s games=%d means=%s", team_name, team_tag, len(games), means)
    return features


async def load_premier_prediction_features(blue_name, blue_tag, red_name, red_tag):
    blue_ids, red_ids = await asyncio.gather(
        get_recent_premier_match_ids(blue_name, blue_tag),
        get_recent_premier_match_ids(red_name, red_tag),
    )
    # 양 팀이 맞붙었던 경기도 요청당 한 번만 조회한다. Henrik의 기존 TTL 캐시도 재사용.
    ids = list(dict.fromkeys(blue_ids + red_ids))
    for match_id in ids:
        logger.debug("[PREMIER MATCH] match_id=%s", match_id)
    details = dict(zip(ids, await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in ids))))
    results, errors = [], []
    # 이미 조회한 양 팀 데이터를 모두 진단한다. Blue 실패로 Red 로그가 사라지지 않게 한다.
    for name, tag, team_ids in ((blue_name, blue_tag, blue_ids), (red_name, red_tag, red_ids)):
        try:
            results.append(build_premier_player_features([details[mid] for mid in team_ids], name, tag, team_ids))
        except ValueError as exc:
            errors.append(exc)
    if errors:
        raise errors[0]
    return tuple(results)


async def resolve_recent_roster(team_name: str, team_tag: str) -> tuple[dict | None, list[dict]]:
    """(team_info, roster) 반환. 팀 자체가 없으면 (None, []), 있지만 최근 매치에서 5인
    로스터를 못 찾으면 (team_info, [])."""
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(team_name, team_tag),
        henrik_api.get_premier_team_history(team_name, team_tag),
    )
    if not team_info:
        return None, []

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:ROSTER_LOOKUP_LIMIT] if m.get("id")]

    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for match_id in match_ids:
        match = await henrik_api.get_match_detail(match_id)
        if not match:
            continue
        teams = match.get("teams") or {}
        for side in ("red", "blue"):
            roster = (teams.get(side) or {}).get("roster") or {}
            # 2026-09-14 버그 수정: roster.get("name")도 strip() 처리 - Henrik roster.name에
            # 공백이 붙은 팀이 실제로 있어(예: "XLA  ") 안 하면 비교가 항상 실패했다.
            if (
                str(roster.get("name", "")).strip().lower() != name_l
                or str(roster.get("tag", "")).strip().lower() != tag_l
            ):
                continue
            puuids = set(roster.get("members") or [])
            all_players = (match.get("players") or {}).get("all_players") or []
            roster_players = [p for p in all_players if p.get("puuid") in puuids]
            if len(roster_players) == 5:
                return team_info, [{"name": p.get("name"), "tag": p.get("tag")} for p in roster_players]

    return team_info, []


async def resolve_recent_opponent(team_name: str, team_tag: str) -> dict | None:
    """team_name/team_tag의 가장 최근 매치 1건에서 상대팀(name/tag)을 찾는다.
    매치 이력이 없거나, 그 매치 상세에서 우리 팀 로스터를 못 찾으면 None
    (팀 자체가 없는 경우도 team_info가 None이라 여기서 None)."""
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(team_name, team_tag),
        henrik_api.get_premier_team_history(team_name, team_tag),
    )
    if not team_info:
        return None

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    if not recent or not recent[0].get("id"):
        return None

    match = await henrik_api.get_match_detail(recent[0]["id"])
    if not match:
        return None

    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    # 2026-09-14 버그 수정: roster.get("name")도 strip() 처리(위 resolve_recent_roster와
    # 동일 이유) - Henrik roster.name에 공백이 붙은 팀이 실제로 있어(예: "XLA  ") 안 하면
    # 비교가 항상 실패했다.
    our_side = next(
        (
            side for side in ("red", "blue")
            if str((teams.get(side) or {}).get("roster", {}).get("name", "")).strip().lower() == name_l
            and str((teams.get(side) or {}).get("roster", {}).get("tag", "")).strip().lower() == tag_l
        ),
        None,
    )
    if our_side is None:
        return None

    opp_side = "blue" if our_side == "red" else "red"
    opp_roster = (teams.get(opp_side) or {}).get("roster") or {}
    opp_name, opp_tag = opp_roster.get("name"), opp_roster.get("tag")
    return {"teamName": opp_name, "teamTag": opp_tag} if opp_name and opp_tag else None


def save_prediction(
    db: Session,
    *,
    team_a_id: str,
    opponent_team_name: str,
    opponent_team_tag: str,
    predicted_winrate_a: float,
    predicted_winrate_b: float,
    model_version: str,
    feature_snapshot: dict,
) -> Prediction:
    """예측 결과 1건 저장. 상대팀이 이 서비스 가입 계정이면 team_b_id도 함께 채우고,
    아니면(원래 이 기능의 정상적인 주 사용 케이스) NULL로 남긴다 - opponent_team_name/
    opponent_team_tag가 가입 여부와 무관하게 항상 상대팀을 식별해준다."""
    opponent = (
        db.query(Team)
        .filter(Team.team_name == opponent_team_name, Team.team_tag == opponent_team_tag)
        .first()
    )
    row = Prediction(
        team_a_id=team_a_id,
        team_b_id=opponent.team_id if opponent else None,
        opponent_team_name=opponent_team_name,
        opponent_team_tag=opponent_team_tag,
        predicted_winrate_a=predicted_winrate_a,
        predicted_winrate_b=predicted_winrate_b,
        model_version=model_version,
        feature_snapshot_json=feature_snapshot,
        created_at=_now_kst(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
