"""
승부 예측(routers/predict.py) 지원 서비스.
- resolve_recent_roster: team_name/team_tag의 최근 매치에서 5인 로스터(name/tag)를 찾는다.
  teams 테이블엔 로스터 매핑이 없어서(팀 대표를 개인 계정 단위로 묶지 않기로 한 결정,
  services/team_profile.py와 동일 전제) 예측할 때마다 Henrik 매치 이력에서 다시 뽑아야 한다.
- save_prediction: 예측 결과 1건을 predictions 테이블에 저장.
로스터 5명이 정해진 뒤의 피처 계산/추론(ml/rolling.py, ml/predictor.py)은 건드리지 않는다.
"""
import asyncio

from sqlalchemy.orm import Session

from models.prediction import Prediction
from models.team import Team
from services import henrik_api

# 이력에서 가장 최근 매치부터 몇 건까지 살펴보며 5인 로스터가 온전히 잡히는 매치를 찾을지.
# services/team_profile.py의 MATCH_HISTORY_LIMIT(10)보다 훨씬 적게 잡았다 - 로스터 5명만
# 있으면 바로 멈추므로 대부분 첫 매치에서 끝나고, 여러 건을 동시에 불러올 필요도 없다.
ROSTER_LOOKUP_LIMIT = 5


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
            if str(roster.get("name", "")).lower() != name_l or str(roster.get("tag", "")).lower() != tag_l:
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
    our_side = next(
        (
            side for side in ("red", "blue")
            if str((teams.get(side) or {}).get("roster", {}).get("name", "")).lower() == name_l
            and str((teams.get(side) or {}).get("roster", {}).get("tag", "")).lower() == tag_l
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
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
