"""
팀 프로필 상세 페이지(메인화면 팀 검색 → 진입). 개인 검색과 API가 섞이지 않도록
prefix/파일명/함수명을 전부 팀 전용으로 분리했다 (players.py/player_profile.py와 쌍).

미가입(비회원) 팀 데이터 DB 캐싱은 아직 넣지 않았다 - 매 요청마다 Henrik을 그대로
호출한다 (team_search.md의 캐싱 전략 검토 참고, 로그인 기능 붙기 전까지는 보류).
"""
import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import SessionLocal, get_db
from ml import engagement_predictor
from models.team import Team
from routers.auth import get_current_team
from services import henrik_api, match_history, team_engagement_cache
from services.team_profile import (
    MATCH_HISTORY_LIMIT,
    QUICK_ANALYSIS_MATCH_LIMIT,
    build_quick_analysis,
    build_team_profile,
    build_team_header
)


def _accumulate_match_history(
    db: Session, match_ids: list[str], match_details: list, started_at_by_id: dict[str, str] | None = None
) -> None:
    """조회하는 김에 matches/match_player_stats + team_engagement_cache에 쌓는다
    (opportunistic 캐싱, server/승부예측_성능_분석.md 7-2-1번) - 승부예측 분석 탭 ③번
    모델 학습용 데이터 축적이 목적. 화면 응답은 이미 받아온 match_details만으로 완성되고
    이 함수의 성공 여부와는 무관하므로(BackgroundTasks로 응답 이후에 돈다,
    _accumulate_match_history_task 참고), 실패해도 조용히 넘어가고(단, 세션은 롤백해서
    이후 쿼리가 깨지지 않게 함) 로그만 남긴다.
    started_at_by_id: 프리미어 히스토리(league_matches)의 started_at - match_player_stats.
    started_at 채우는 용도(services/match_history.py 참고)."""
    started_at_by_id = started_at_by_id or {}
    for match_id, detail in zip(match_ids, match_details):
        if not detail:
            continue
        try:
            match_history.upsert_match_history(db, match_id, detail, started_at_by_id.get(match_id))
        except Exception as e:
            db.rollback()
            print(f"  [match_history] upsert 실패(match_id={match_id}): {e}")


def _accumulate_match_history_task(
    match_ids: list[str], match_details: list, started_at_by_id: dict[str, str] | None = None
) -> None:
    """FastAPI BackgroundTasks 진입점 - 응답을 보낸 뒤에 실행되므로 요청 스코프 세션
    (Depends(get_db))은 이미 닫혔을 수 있어 재사용하지 않고 직접 세션을 열고 닫는다
    (services/match_sync.py::sync_team_match_history와 동일 패턴).

    2026-09-10: 원래 get_team_profile/get_team_analysis가 응답을 만들기 전에 이 write-
    through를 동기로 기다렸는데, 매치 10건 기준 실측 ~2.5초가 걸려(DB 왕복 다수 - 팀 조회/
    선수별 upsert/team_engagement_cache 커밋 등) 응답 자체가 그만큼 늦어졌다(팀 전적 검색 시
    ACT/매치 목록이 늦게 뜨는 원인). 이 write-through 결과는 응답 어디에도 안 쓰이므로
    (build_team_profile은 이미 받아온 match_details만 씀) 백그라운드로 미뤄도 손해가 없다."""
    db = SessionLocal()
    try:
        _accumulate_match_history(db, match_ids, match_details, started_at_by_id)
    finally:
        db.close()


router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_name}/{team_tag}")
async def get_team_profile(
    team_name: str, team_tag: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """팀 프로필 전체 조회. 팀 기본 정보(get_premier_team)와 매치 이력(get_premier_team_history)을
    동시에 불러온 뒤, 이력에서 얻은 최근 매치 id들로 매치 상세(get_match_detail)를 다시 동시에
    불러온다 - 상세 없이는 맵/스코어/로스터 스탯을 알 수 없어 이력 조회가 먼저 끝나야 한다."""
    clean_name = team_name.strip()
    clean_tag = team_tag.strip()
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(clean_name, clean_tag),
        henrik_api.get_premier_team_history(clean_name, clean_tag),
    )
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:MATCH_HISTORY_LIMIT] if m.get("id")]
    started_at_by_id = {m["id"]: m.get("started_at") for m in recent if m.get("id")}

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))
    # write-through는 응답 내용에 안 쓰이므로(build_team_profile은 match_details만 씀)
    # 백그라운드로 미룬다 - 동기로 기다리면 매치 10건 기준 ~2.5초가 응답에 그대로 더해진다
    # (_accumulate_match_history_task 참고).
    background_tasks.add_task(
        _accumulate_match_history_task, match_ids, list(match_details), started_at_by_id
    )

    return build_team_profile(
        db,
        team_name=clean_name,
        team_tag=clean_tag,
        team_info=team_info,
        match_details=list(match_details),
    )


@router.get("/{team_name}/{team_tag}/quick-analysis")
async def get_team_quick_analysis(
    team_name: str, team_tag: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """QuickAnalysisModal(통합검색 '팀명#태그' 팝업)용 최근 5게임 요약 조회.
    get_team_profile과 동일하게 team_info + history를 동시에 불러온 뒤 최근 매치 상세를
    한 번 더 동시에 불러오지만, 매치 건수는 QUICK_ANALYSIS_MATCH_LIMIT(5)로 더 적게 가져온다."""
    clean_name = team_name.strip()
    clean_tag = team_tag.strip()
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(clean_name, clean_tag),
        henrik_api.get_premier_team_history(clean_name, clean_tag),
    )
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:QUICK_ANALYSIS_MATCH_LIMIT] if m.get("id")]
    started_at_by_id = {m["id"]: m.get("started_at") for m in recent if m.get("id")}

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))
    # get_team_profile/get_team_analysis와 동일한 이유로 write-through를 백그라운드로 미룬다 -
    # 이 팝업은 원래 team_engagement_cache에 전혀 안 쌓였는데(quick-analysis만 유일하게
    # 이 호출이 빠져 있었음), 여기서 조회한 매치도 다른 검색 경로와 똑같이 학습 데이터로
    # 누적되도록 추가한다(_accumulate_match_history_task 참고). QUICK_ANALYSIS_MATCH_LIMIT(5)
    # 건뿐이라 write-through 비용도 작다.
    background_tasks.add_task(
        _accumulate_match_history_task, match_ids, list(match_details), started_at_by_id
    )

    return build_quick_analysis(
        db,
        team_name=clean_name,
        team_tag=clean_tag,
        team_info=team_info,
        match_details=list(match_details),
    )


@router.get("/{team_name}/{team_tag}/header")
async def get_team_header(team_name: str, team_tag: str):
    """성능 개선(엔드포인트 분리) - ProfileHeader(팀 로고/이름/디비전/누적 승률)만 필요할 때
    쓰는 경량 엔드포인트. get_team_profile은 매치 이력+상세 10건까지 다 기다려야 응답이
    나가서(~2.5~3.1s, 실측) 팀 로고가 늦게 뜨는 원인이었는데, 이 엔드포인트는 get_premier_team
    한 번(~0.3~0.6s, 대부분 search.py의 존재확인 프리페치로 이미 캐시돼 있어 더 빠름)만으로
    응답한다. TeamProfilePage가 이 엔드포인트와 get_team_profile을 동시에 호출해서, 먼저
    도착하는 이 응답으로 헤더부터 그리고 나머지(매치 이력/순위 등)는 get_team_profile이
    도착하는 대로 채운다."""
    team_info = await henrik_api.get_premier_team(team_name, team_tag)
    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")
    return build_team_header(team_name, team_tag, team_info)


@router.get("/{team_name}/{team_tag}/analysis")
async def get_team_analysis(
    team_name: str,
    team_tag: str,
    background_tasks: BackgroundTasks,
    current: Team = Depends(get_current_team),
    db: Session = Depends(get_db),
):
    """상대 팀 분석 및 승부 예측 탭 전용 상세 통계 조회.
    get_team_profile과 동일한 매치 히스토리를 바탕으로 분석 탭에 필요한 데이터를 구성한다.

    2026-09-08: Depends(get_current_team) 추가 - engagementPrediction(③번 교전 매치업
    예측, server/승부예측_성능_분석.md 6~9번)이 "우리팀 vs 상대팀"을 비교하려면 로그인한
    팀이 누군지 알아야 한다. 이 엔드포인트를 쓰는 프론트 화면은 MatchPredictionPage뿐이고
    그 라우트는 이미 ProtectedRoute(로그인 필수)라서 실제 접근 패턴은 안 바뀐다 - 9-4번에
    적어둔 "구조적 변경" 우려와 달리 실질적인 파급 효과는 없는 것으로 확인."""

    clean_name = team_name.strip()
    clean_tag = team_tag.strip()

    #print(f"===== DEBUG: API Called for team: {clean_name}#{clean_tag} =====")

    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(clean_name, clean_tag),
        henrik_api.get_premier_team_history(clean_name, clean_tag),
    )

    # print(f"===== DEBUG: team_info loaded: {bool(team_info)} =====")
    # print(f"===== DEBUG: history raw data: {history} =====")

    if not team_info:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")

    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:MATCH_HISTORY_LIMIT] if m.get("id")]
    started_at_by_id = {m["id"]: m.get("started_at") for m in recent if m.get("id")}

    # print(f"===== DEBUG: extracted match_ids: {match_ids} =====")

    match_details = await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))
    # write-through는 응답에 안 쓰이므로(engagementPrediction의 "우리팀" 몫은 이미 캐시된
    # team_engagement_cache를 읽을 뿐, 이 요청에서 방금 upsert한 값을 기다리지 않음)
    # 백그라운드로 미룬다 - get_team_profile과 동일 이유(_accumulate_match_history_task 참고).
    background_tasks.add_task(
        _accumulate_match_history_task, match_ids, list(match_details), started_at_by_id
    )

    # print(f"===== DEBUG: match_details fetched count: {len(match_details)} =====")

        # 라운드 데이터 구조(공격/수비 사이드, economy 등) 확인용 임시 디버그 로그.
    # roundInfo의 공격/수비/에코 승률 구현이 끝나면 삭제할 것.
    # print("===== DEBUG: SAMPLE ROUND (planted round, top-level keys only) =====")
    sample_match = next((m for m in match_details if m), None)
    if sample_match:

        kills = sample_match.get("kills") or []
        if kills:
            print("===== DEBUG: SAMPLE KILL EVENT =====")
            print(json.dumps(kills[0], indent=2, ensure_ascii=False))
        else:
            print("NO KILLS FOUND IN THIS MATCH")
            
        rounds = sample_match.get("rounds") or []
        planted_round = next((r for r in rounds if r.get("bomb_planted")), None)
        if planted_round:
            trimmed = {k: v for k, v in planted_round.items() if k not in ("player_stats", "player_locations")}
            # print(json.dumps(trimmed, indent=2, ensure_ascii=False))
        else:
            print("NO PLANTED ROUND FOUND IN THIS MATCH")
    else:
        print("NO VALID MATCH")

    profile = build_team_profile(
        db,
        team_name=clean_name,
        team_tag=clean_tag,
        team_info=team_info,
        match_details=list(match_details),
    )

    # 맵 이미지 매칭 키 디버깅용 로그 추가
    #print("===== DEBUG: mapInfoByMap keys =====")
    # print(list(profile.get("mapInfoByMap", {}).keys()))

    #print("===== DEBUG: FINAL PROFILE RESPONSE =====")
    # print("roundInfo:", profile.get("roundInfo"))
    # print("mapInfoByMap:", profile.get("mapInfoByMap"))

    # 0경기(sampleGames <= 0)인 맵을 API 응답 레벨에서 원천적으로 필터링하여 방어
    raw_map_info = profile.get("mapInfoByMap", {})
    filtered_map_info = {
        k: v for k, v in raw_map_info.items() 
        if (v.get("sampleGames") or v.get("games") or 0) > 0
    }

    filtered_map_winrates = [
        m for m in profile.get("mapWinrates", [])
        if (raw_map_info.get(m.get("map"), {}).get("sampleGames") or 0) > 0
    ]

    # ③번 교전 매치업 예측(engagementPrediction, 9-4번) - 상대팀(URL)은 이 요청에서 방금
    # 라이브로 받은 match_details를 그대로 쓰고, 우리팀(current)은 team_engagement_cache
    # (Henrik 호출 없음, DB 쿼리 한 번)를 쓴다 - 우리팀 매치 이력을 여기서 다시 Henrik으로
    # 조회하지 않는 이유는 services/match_sync.py가 회원가입 시점에, services/
    # match_history.py가 팀 프로필/분석 조회 때마다 각각 write-through로 이 캐시를 이미
    # 채워뒀기 때문 - 그 값을 그대로 재사용한다(server/승부예측_성능_분석.md 11번).
    opponent_trade = engagement_predictor.trade_rate_from_matches(list(match_details), clean_name, clean_tag)
    opponent_duelist = engagement_predictor.duelist_acs_from_matches(list(match_details), clean_name, clean_tag)
    our_engagement = team_engagement_cache.get_recent_team_engagement(db, current.team_id)

    engagement_prediction = engagement_predictor.build_engagement_prediction_from_features(
        team_trade_rate=our_engagement["trade_rate"] if our_engagement else None,
        opponent_trade_rate=opponent_trade,
        team_duelist_acs=our_engagement["duelist_acs"] if our_engagement else None,
        opponent_duelist_acs=opponent_duelist,
    )

    return {
        "roundInfo": profile.get("roundInfo", {}),
        "mapWinrates": filtered_map_winrates,
        "mapInfoByMap": filtered_map_info,
        "engagementPrediction": engagement_prediction,
    }
