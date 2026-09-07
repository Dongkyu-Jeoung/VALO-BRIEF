"""
팀 프로필 상세 페이지(메인화면 팀 검색 → 진입). 개인 검색과 API가 섞이지 않도록
prefix/파일명/함수명을 전부 팀 전용으로 분리했다 (players.py/player_profile.py와 쌍).

미가입(비회원) 팀 데이터 DB 캐싱은 아직 넣지 않았다 - 매 요청마다 Henrik을 그대로
호출한다 (team_search.md의 캐싱 전략 검토 참고, 로그인 기능 붙기 전까지는 보류).
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from services import henrik_api
from services.team_profile import (
    MATCH_HISTORY_LIMIT,
    QUICK_ANALYSIS_MATCH_LIMIT,
    build_quick_analysis,
    build_team_profile,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_name}/{team_tag}")
async def get_team_profile(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    """팀 프로필 전체 조회. 팀 기본 정보(get_premier_team)와 매치 이력(get_premier_team_history)을
    동시에 불러온 뒤, 이력에서 얻은 최근 매치 id들로 매치 상세(get_match_detail)를 다시 동시에
    불러온다 - 상세 없이는 맵/스코어/로스터 스탯을 알 수 없어 이력 조회가 먼저 끝나야 한다."""
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(team_name, team_tag),
        henrik_api.get_premier_team_history(team_name, team_tag),
    )
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:MATCH_HISTORY_LIMIT] if m.get("id")]

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))

    return build_team_profile(
        db,
        team_name=team_name,
        team_tag=team_tag,
        team_info=team_info,
        match_details=list(match_details),
    )


@router.get("/{team_name}/{team_tag}/quick-analysis")
async def get_team_quick_analysis(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    """QuickAnalysisModal(통합검색 '팀명#태그' 팝업)용 최근 5게임 요약 조회.
    get_team_profile과 동일하게 team_info + history를 동시에 불러온 뒤 최근 매치 상세를
    한 번 더 동시에 불러오지만, 매치 건수는 QUICK_ANALYSIS_MATCH_LIMIT(5)로 더 적게 가져온다."""
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(team_name, team_tag),
        henrik_api.get_premier_team_history(team_name, team_tag),
    )
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:QUICK_ANALYSIS_MATCH_LIMIT] if m.get("id")]

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))

    return build_quick_analysis(
        db,
        team_name=team_name,
        team_tag=team_tag,
        team_info=team_info,
        match_details=list(match_details),
    )


@router.get("/{team_name}/{team_tag}/analysis")
async def get_team_analysis(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    """상대 팀 분석 및 승부 예측 탭 전용 상세 통계 조회.
    get_team_profile과 동일한 매치 히스토리를 바탕으로 분석 탭에 필요한 데이터를 구성한다."""
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(team_name, team_tag),
        henrik_api.get_premier_team_history(team_name, team_tag),
    )
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:MATCH_HISTORY_LIMIT] if m.get("id")]

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))

    profile = build_team_profile(
        db,
        team_name=team_name,
        team_tag=team_tag,
        team_info=team_info,
        match_details=list(match_details),
    )

    # 맵 이미지 매칭 키 디버깅용 로그 추가
    print("===== DEBUG: mapInfoByMap keys =====")
    print(list(profile.get("mapInfoByMap", {}).keys()))

    return {
        "roundInfo": profile.get("roundInfo", {}),
        "mapWinrates": profile.get("mapWinrates", []),
        "mapInfoByMap": profile.get("mapInfoByMap", {}),
    }