"""
Henrik 매치 상세(v2/match) 하나를 받아서 그 매치 하나만의 트레이드 성공률/듀얼리스트
ACS를 계산해 team_engagement_cache에 (team_id, match_id) 행으로 upsert - 승부예측 분석
탭 ③번(교전 매치업 예측) 모델 학습용 데이터 + "지금 폼" 캐시를 겸한다(server/승부예측_
성능_분석.md 11번, services/team_engagement_cache.py 모듈 docstring 참고).

2026-09-08 재설계: 이전에는 matches/match_player_stats에 매치 원본(로스터별 ACS/킬/
데스 등)을 통째로 저장해두고 그걸 다시 집계해서 team_engagement_cache를 채웠지만,
지금은 원본을 아예 저장하지 않고 받은 자리에서 바로 계산한 값(이 모델에 필요한 두
숫자)만 남긴다 - matches/match_player_stats는 더 이상 이 파이프라인에서 쓰지 않는다
(테이블/모델 정의 자체는 그대로 둠).

"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ml import engagement_predictor
from models.team import Team
from services import team_engagement_cache


def _parse_game_start(value) -> datetime | None:
    """metadata.game_start(epoch 초/밀리초)를 datetime으로. services/team_profile.py::
    _parse_datetime과 동일 로직 - private 함수라 의존하지 않고 여기 따로 둠."""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
    return None


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    """team_name/team_tag로 가입된 teams 행을 찾아 team_id(=Henrik 프리미어 팀 id)를 반환.
    가입 안 된 팀이면 None(team_engagement_cache가 가입 팀만 캐싱하는 이유 그대로)."""
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(Team.team_name == team_name, Team.team_tag == team_tag)
        .first()
    )
    return row[0] if row else None


def upsert_match_history(db: Session, match_id: str, match: dict) -> None:
    if not match_id:
        return

    metadata = match.get("metadata") or {}
    teams = match.get("teams") or {}
    red_roster = (teams.get("red") or {}).get("roster") or {}
    blue_roster = (teams.get("blue") or {}).get("roster") or {}

    team_a_id = _find_team_id(db, red_roster.get("name", ""), red_roster.get("tag", ""))
    team_b_id = _find_team_id(db, blue_roster.get("name", ""), blue_roster.get("tag", ""))
    if not team_a_id and not team_b_id:
        return

    game_start = _parse_game_start(metadata.get("game_start"))

    if team_a_id:
        team_engagement_cache.upsert_match_engagement(
            db, team_a_id, match_id,
            opponent_team_id=team_b_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
        )
    if team_b_id:
        team_engagement_cache.upsert_match_engagement(
            db, team_b_id, match_id,
            opponent_team_id=team_a_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
        )
