"""
로그인한 팀 전용 "우리팀 분석" 페이지. 통계/팀 분석 탭이 구현되어 있다 - 개인 분석/AI
리포트 탭은 아직 이 라우터에 없음(front도 그 탭들은 기존 mock 경로를 그대로 쓴다).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.connection import get_db
from models.team import Team
from routers.auth import get_current_team
from services import my_team_analysis, my_team_stats

router = APIRouter(prefix="/api/my-team", tags=["my-team"])


@router.get("/stats")
def get_my_team_stats(current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """Henrik을 실시간으로 부르지 않고, 회원가입 시 services/match_sync.py가 미리
    캐싱해둔 matches/match_player_stats를 그대로 읽어 응답한다."""
    return my_team_stats.build_my_team_stats(db, current)


@router.get("/analysis")
def get_my_team_analysis(current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """team_stats_summary에 캐싱된 값을 읽어 응답한다. 캐시가 비어있으면(첫 진입)
    matches/match_player_stats에서 라운드 단위로 계산해 채운 뒤 응답한다."""
    return my_team_analysis.build_my_team_analysis(db, current.team_id)
