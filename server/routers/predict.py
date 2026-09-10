"""
승부 예측 (Frame 07, 08). 엔드포인트 두 개로 나뉜다.

- POST /api/predict: ml 파이프라인 자체를 테스트하기 위한 저수준 엔드포인트(5v5 로스터를
  직접 입력받음) - 화면에서 선수 10명을 직접 타이핑하게 할 수 없어서 프론트는 이걸 쓰지
  않는다(ML 개발/디버깅용으로 남겨둠). DB 저장 없음.
- GET /api/predict/{team_name}/{team_tag}: 프론트(MatchPredictionPage, api/prediction.js)가
  실제로 호출하는 엔드포인트. 우리 팀 DB 로스터를 우선 사용하고 부족하면 Henrik으로
  보완한다. 상대 팀 로스터를 조회한 뒤 모델 예측 결과를 반환한다.
"""
import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from database.connection import SessionLocal
from ml.predictor import predict_blue_win, create_prediction_checkpoint
from ml.db_roster import resolve_recent_roster_from_db
from models.team import Team
from routers.auth import get_current_team
from schema.predict import PredictRequest, PredictResponse
from services import predict_service
from services.prediction_refill import schedule_refill
from services.henrik_api import HenrikRateLimitError

router = APIRouter(prefix="/api/predict", tags=["Predict"])

logger = logging.getLogger(__name__)


@router.post("", response_model=PredictResponse)
def predict(request: PredictRequest):
    """ml 파이프라인 저수준 테스트용(5v5 로스터 직접 입력) - DB 저장 없음."""
    try:
        result = predict_blue_win(
            blue_team=[p.model_dump() for p in request.blue_team],
            red_team=[p.model_dump() for p in request.red_team],
        )
        return result
    except HenrikRateLimitError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-opponent")
async def get_recent_opponent(current: Team = Depends(get_current_team)):
    """로그인한 팀의 가장 최근 프리미어 매치 상대팀을 찾는다."""
    opponent = await predict_service.resolve_recent_opponent(current.team_name, current.team_tag)
    if opponent is None:
        raise HTTPException(status_code=404, detail="최근 매치 상대팀을 찾을 수 없습니다.")
    return opponent


def _load_our_roster(team_id):
    with SessionLocal() as db:
        return resolve_recent_roster_from_db(db, team_id)


def _predict_with_db(our_roster, opp_roster, checkpoint=None, db_missing_players=None):
    with SessionLocal() as db:
        return predict_blue_win(our_roster, opp_roster, db=db, debug_checkpoint=checkpoint,
                                db_missing_players=db_missing_players)


@router.get("/{team_name}/{team_tag}")
async def predict_match(
    team_name: str,
    team_tag: str,
    current: Team = Depends(get_current_team),
):
    started = time.perf_counter()
    checkpoint = create_prediction_checkpoint()
    db_missing_players = []
    refill_team = (current.team_id, current.team_name, current.team_tag)
    checkpoint("GET 예측 요청 처리 시작 (인증 이후)")
    
    try:
        checkpoint("우리 팀 DB 로스터 조회 시작")
        our_team_info, our_roster = await asyncio.to_thread(_load_our_roster, current.team_id)
        checkpoint(f"우리 팀 DB 로스터 조회 완료: {len(our_roster)}명")
        
        # 만약 DB 로스터가 부족해 API로 조회할 경우를 대비해 우리팀 정보(team_info)도 함께 확보
        from services.henrik_api import get_premier_team
        our_full_info = await get_premier_team(current.team_name, current.team_tag)
        
        if len(our_roster) != 5:
            checkpoint("우리 팀 API 로스터 조회 시작")
            our_full_info, our_roster = await predict_service.resolve_recent_roster(
                current.team_name, current.team_tag
            )
            checkpoint(f"우리 팀 API 로스터 조회 완료: {len(our_roster)}명")
        if len(our_roster) != 5:
            raise HTTPException(status_code=422, detail="우리 팀의 최근 5인 로스터를 찾지 못했습니다.")

        checkpoint("상대 팀 API 로스터 조회 시작")
        opp_info, opp_roster = await predict_service.resolve_recent_roster(team_name, team_tag)
        checkpoint(f"상대 팀 API 로스터 조회 완료: {len(opp_roster)}명")
        if opp_info is None:
            raise HTTPException(status_code=404, detail="존재하지 않는 프리미어 팀입니다.")
        if len(opp_roster) != 5:
            raise HTTPException(status_code=422, detail="상대 팀의 최근 5인 로스터를 찾지 못했습니다.")

        checkpoint("예측 작업 스레드 호출")
        result = await asyncio.to_thread(_predict_with_db, our_roster, opp_roster, checkpoint, db_missing_players)
        
        # 양 팀 커스텀 로고 이미지 추출 후 결과 딕셔너리에 병합
        our_customization = (our_full_info or {}).get("customization") or {}
        opp_customization = (opp_info or {}).get("customization") or {}
        
        our_logo = our_customization.get("image")
        opp_logo = opp_customization.get("image")

        # 프론트엔드가 우리팀/상대팀 객체 내부에서 logoUrl을 바로 참조할 수 있도록 구조 반영
        result["ourTeam"] = {
            "name": current.team_name,
            "tag": current.team_tag,
            "logoUrl": our_logo,
        }
        result["opponentTeam"] = {
            "name": team_name,
            "tag": team_tag,
            "logoUrl": opp_logo,
            "ratingIconUrl": opp_logo,
        }

        checkpoint("예측 결과 반환 준비 완료")
        return result
    except (HenrikRateLimitError, HTTPException) as exc:
        checkpoint(f"요청 처리 실패: {type(exc).__name__}")
        raise
    except ValueError as exc:
        checkpoint("요청 처리 실패: ValueError")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        checkpoint(f"요청 처리 실패: {type(exc).__name__}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        schedule_refill(*refill_team, db_missing_players, checkpoint)
        checkpoint("GET 예측 요청 처리 종료")
        logger.info("[PREDICTION REQUEST TIME] %.2fs", time.perf_counter() - started)