"""
팀 프로필 상세 페이지(메인화면 팀 검색 → 진입). 개인 검색과 API가 섞이지 않도록
prefix/파일명/함수명을 전부 팀 전용으로 분리했다 (players.py/player_profile.py와 쌍).

미가입(비회원) 팀 데이터는 DB 캐싱 없이 매 요청마다 Henrik을 그대로 호출한다
(team_search.md의 캐싱 전략 검토 참고).
"""
import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import SessionLocal, get_db
from ml import engagement_predictor
from models.team import Team
from routers.auth import get_current_team
from services import henrik_api, match_history, opponent_ai_report, predict_service, prediction_cache, team_engagement_cache
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
    """Persist compact engagement summaries from already fetched API responses.
    Raw match rows and player statistics are not stored. Roll back failures so
    the next summary can still be processed."""
    started_at_by_id = started_at_by_id or {}
    for match_id, detail in zip(match_ids, match_details):
        if not detail:
            continue
        try:
            match_history.upsert_match_engagement_summary(db, match_id, detail, started_at_by_id.get(match_id))
        except Exception as e:
            db.rollback()
            print(f"  [match_history] upsert 실패(match_id={match_id}): {e}")


def _accumulate_match_history_task(
    match_ids: list[str], match_details: list, started_at_by_id: dict[str, str] | None = None
) -> None:
    """Save engagement summaries after the response, using a separate DB session."""
    db = SessionLocal()
    try:
        _accumulate_match_history(db, match_ids, match_details, started_at_by_id)
    finally:
        db.close()


router = APIRouter(prefix="/api/teams", tags=["teams"])
logger = logging.getLogger(__name__)

# get_team_analysis 캐시 키에 쓰는 버전 태그 - 응답 스키마가 바뀌면(engagementPrediction
# 구조 변경 등) 올려서 이전 캐시가 새 형식과 섞여 반환되지 않게 한다(routers/predict.py의
# MATCH_MODEL_VERSION과 같은 역할, services/prediction_cache.py 참고).
TEAM_ANALYSIS_CACHE_VERSION = "v1"


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

    로그인이 필요하다(Depends(get_current_team)) - engagementPrediction(교전 매치업 예측)이
    "우리팀 vs 상대팀"을 비교하려면 로그인한 팀이 누군지 알아야 한다.

    Henrik 팀 조회 + 이력 + 매치 상세(건당 ~1.3MB) 여러 건을 매번 실시간으로 불러오는 무거운
    엔드포인트라 routers/predict.py::predict_match와 같은 이유로 prediction_cache(40분 TTL,
    동시요청 공유)를 적용했다. 캐시 히트 시엔 _compute_team_analysis가 실행되지 않으므로
    write-through/predictions 테이블 저장도 40분에 한 번만(최초 호출자에 한해) 일어나,
    매 조회마다 predictions에 중복 행이 쌓이던 문제도 같이 줄어든다."""
    clean_name = team_name.strip()
    clean_tag = team_tag.strip()
    key = (
        current.team_id, current.team_name, current.team_tag,
        clean_name, clean_tag, TEAM_ANALYSIS_CACHE_VERSION,
    )
    return await prediction_cache.get_or_create(
        key, lambda: _compute_team_analysis(clean_name, clean_tag, current, db, background_tasks),
    )


async def _compute_team_analysis(
    clean_name: str, clean_tag: str, current: Team, db: Session, background_tasks: BackgroundTasks,
):
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
    # write-through는 응답에 안 쓰이므로(engagementPrediction의 "우리팀" 몫은 이미 캐시된
    # team_engagement_cache를 읽을 뿐, 이 요청에서 방금 upsert한 값을 기다리지 않음)
    # 백그라운드로 미룬다 - get_team_profile과 동일 이유(_accumulate_match_history_task 참고).
    background_tasks.add_task(
        _accumulate_match_history_task, match_ids, list(match_details), started_at_by_id
    )

    sample_match = next((m for m in match_details if m), None)
    if sample_match:
        kills = sample_match.get("kills") or []
        rounds = sample_match.get("rounds") or []
        planted_round = next((r for r in rounds if r.get("bomb_planted")), None)
        if planted_round:
            trimmed = {k: v for k, v in planted_round.items() if k not in ("player_stats", "player_locations")}
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
    # 채워뒀기 때문 - 그 값을 그대로 재사용한다
    opponent_trade = engagement_predictor.trade_rate_from_matches(list(match_details), clean_name, clean_tag)
    opponent_duelist = engagement_predictor.duelist_acs_from_matches(list(match_details), clean_name, clean_tag)
    opponent_win_rate = engagement_predictor.win_rate_from_matches(list(match_details), clean_name, clean_tag)
    our_engagement = team_engagement_cache.get_recent_team_engagement(db, current.team_id)

    engagement_prediction = engagement_predictor.build_engagement_prediction_from_features(
        team_trade_rate=our_engagement["trade_rate"] if our_engagement else None,
        opponent_trade_rate=opponent_trade,
        team_duelist_acs=our_engagement["duelist_acs"] if our_engagement else None,
        opponent_duelist_acs=opponent_duelist,
        team_win_rate=our_engagement["win_rate"] if our_engagement else None,
        opponent_win_rate=opponent_win_rate,
    )

    # 교전 매치업 예측도 predictions 테이블에 남긴다(승부예측/predict.py 쪽과 같은 이유 -
    # 지금까지는 save_prediction()을 아무도 안 불러서 이 테이블이 비어 있었다). trade/
    # duelistMatchup만으로는 "승률"이라 부를 값이 없어서, 실제 승률 추정치인
    # finalPrediction(메타 모델 출력)이 있을 때만 저장한다 - 메타 모델이 아직 없으면
    # (표본 부족) 조용히 건너뛴다. 저장 실패가 화면 응답을 막으면 안 되므로 예외를 삼킨다.
    if engagement_prediction and "finalPrediction" in engagement_prediction:
        try:
            final = engagement_prediction["finalPrediction"]
            predict_service.save_prediction(
                db,
                team_a_id=current.team_id,
                opponent_team_name=clean_name,
                opponent_team_tag=clean_tag,
                predicted_winrate_a=final["ourWinRate"],
                predicted_winrate_b=final["theirWinRate"],
                model_version=final["modelVersion"],
                feature_snapshot=engagement_prediction,
            )
        except Exception:
            logger.exception("교전 예측 결과 저장 실패(predictions 테이블) - 응답에는 영향 없음")

    return {
        "roundInfo": profile.get("roundInfo", {}),
        "mapWinrates": filtered_map_winrates,
        "mapInfoByMap": filtered_map_info,
        "engagementPrediction": engagement_prediction,
    }


@router.get("/{team_name}/{team_tag}/ai-report")
async def get_team_ai_report(
    team_name: str,
    team_tag: str,
    background_tasks: BackgroundTasks,
    current: Team = Depends(get_current_team),
    db: Session = Depends(get_db),
):
    """승부예측 페이지 "AI 리포트" 탭(상대팀 인사이트) - services/opponent_ai_report.py 참고.
    실제 Claude 생성은 20~45초 걸려이 요청 안에서 기다리지 않는다 -
    캐시가 있으면 {"status":"ready","report":{...}}를 바로 주고, 없으면 백그라운드로
    생성을 시작시키고 {"status":"generating"}을(를) 바로 준다(front가 몇 초 간격으로
    다시 호출해 폴링). 상대팀 기준정보(team_engagement_cache)가 아직 DB에 없으면(한 번도
    검색/조회된 적 없는 팀) {"status":"not_ready"}를 200으로 내려준다 - 이건 에러가
    아니라 "아직 준비 안 됨"인 정상 상태라, HTTPException으로 던지면 withFallback이
    실패로 착각해 mock으로 대체해버린다(진짜 "준비 중" 안내 대신 가짜 데이터가 보이게 됨)."""
    return await opponent_ai_report.get_or_start_opponent_ai_report(db, current, team_name, team_tag, background_tasks)
