"""
로그인한 팀 전용 "우리팀 분석" 페이지. 통계/팀 분석/개인 분석(목록+상세) 탭이 구현되어
있다 - AI 리포트 탭은 아직 이 라우터에 없음(front도 그 부분은 기존 mock 경로를 그대로 쓴다).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.connection import get_db
from models.team import Team
from routers.auth import get_current_team
from services import my_team_analysis, my_team_player_detail, my_team_players, my_team_stats

router = APIRouter(prefix="/api/my-team", tags=["my-team"])


@router.get("/stats")
def get_my_team_stats(current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """Henrik을 실시간으로 부르지 않고, 회원가입 시 services/match_sync.py가 미리
    캐싱해둔 matches/match_player_stats를 그대로 읽어 응답한다."""
    return my_team_stats.build_my_team_stats(db, current)


@router.get("/players")
async def get_my_team_players(current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """match_player_stats를 즉시 집계해 응답한다. riot_accounts에 아바타/티어가 아직
    없는 선수(팀 동기화 경로가 안 채운 경우)는 이번 조회에서 한 번만 Henrik을 불러 채운다
    (services/my_team_players.py 참고)."""
    return await my_team_players.build_my_team_players(db, current)


@router.get("/players/{puuid}")
def get_my_team_player_detail(puuid: str, current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """player_stats_summary에 캐싱된 값을 읽어 응답한다. 캐시가 비어있으면(첫 진입)
    matches.round_detail_json/match_player_stats에서 계산해 채운 뒤 응답한다
    (services/my_team_player_detail.py 참고). puuid가 이 팀 로스터가 아니면 404."""
    detail = my_team_player_detail.build_my_team_player_detail(db, current.team_id, puuid)
    if detail is None:
        raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")
    return detail


@router.get("/analysis")
def get_my_team_analysis(current: Team = Depends(get_current_team), db: Session = Depends(get_db)):
    """team_stats_summary에 캐싱된 값을 읽어 응답한다. 캐시가 비어있으면(첫 진입)
    matches/match_player_stats에서 라운드 단위로 계산해 채운 뒤 응답한다."""
    return my_team_analysis.build_my_team_analysis(db, current.team_id)
