"""
승부 예측 (Frame 07, 08). 엔드포인트 두 개로 나뉜다.

- POST /api/predict: ml 파이프라인 자체를 테스트하기 위한 저수준 엔드포인트(5v5 로스터를
  직접 입력받음) - 화면에서 선수 10명을 직접 타이핑하게 할 수 없어서 프론트는 이걸 쓰지
  않는다(ML 개발/디버깅용으로 남겨둠). DB 저장 없음.
- GET /api/predict/{team_name}/{team_tag}: 프론트(MatchPredictionPage, api/prediction.js)가
  실제로 호출하는 엔드포인트. 양 팀의 최근 Premier 3~5경기를 집계하여 예측한다.
"""
import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from ml.predictor import predict_blue_win, predict_from_player_features, create_prediction_checkpoint
from models.team import Team
from routers.auth import get_current_team
from schema.predict import PredictRequest, PredictResponse
from services import predict_service
from services.henrik_api import HenrikRateLimitError

router = APIRouter(prefix="/api/predict", tags=["Predict"])

logger = logging.getLogger(__name__)

# predictions.model_version에 남길 값 - 2026-09-07~09에 이미 이 이름으로 21건이 쌓여
# 있었다(당시엔 save_prediction() 호출부가 있었는데 이후 리팩터링 중에 빠진 것으로
# 보임). ml/model_loader.py가 로드하는 모델(models/xgboost_valorant.pkl)이 그때와
# 같은 파일이라 새 문자열을 만들지 않고 기존 값을 그대로 이어서 쓴다 - model_version
# 기준으로 묶어서 볼 때 과거 데이터와 끊기지 않게 하기 위함.
MATCH_MODEL_VERSION = "xgboost-v1"


def _save_prediction_result(team_a_id, team_name, team_tag, result) -> None:
    """예측 결과 1건을 predictions 테이블에 남긴다(재학습/적중률 분석용 원본 - 지금까지는
    save_prediction()이 구현만 되고 호출되는 곳이 없어 이 테이블이 비어 있었다). 저장
    실패가 예측 응답 자체를 막으면 안 되므로 호출부가 try/except로 감싼다."""
    with SessionLocal() as db:
        predict_service.save_prediction(
            db,
            team_a_id=team_a_id,
            opponent_team_name=team_name,
            opponent_team_tag=team_tag,
            predicted_winrate_a=result["blue_win_probability"],
            predicted_winrate_b=round(100 - result["blue_win_probability"], 1),
            model_version=MATCH_MODEL_VERSION,
            feature_snapshot={
                "blue_summary": result.get("blue_summary"),
                "red_summary": result.get("red_summary"),
            },
        )


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


@router.get("/{team_name}/{team_tag}")
async def predict_match(
    team_name: str,
    team_tag: str,
    current: Team = Depends(get_current_team),
):
    started = time.perf_counter()
    checkpoint = create_prediction_checkpoint()
    checkpoint("GET 예측 요청 처리 시작 (인증 이후)")
    
    try:
        from services.henrik_api import get_premier_team
        our_full_info, opp_info = await asyncio.gather(
            get_premier_team(current.team_name, current.team_tag),
            get_premier_team(team_name, team_tag),
        )
        if not our_full_info or not opp_info:
            raise HTTPException(status_code=404, detail="존재하지 않는 프리미어 팀입니다.")
        blue_players, red_players = await predict_service.load_premier_prediction_features(
            current.team_name, current.team_tag, team_name, team_tag,
        )
        result = await asyncio.to_thread(predict_from_player_features, blue_players, red_players)

        checkpoint("예측 작업 스레드 호출")
        result = await asyncio.to_thread(_predict_with_db, our_roster, opp_roster, checkpoint, db_missing_players)

        try:
            await asyncio.to_thread(_save_prediction_result, current.team_id, team_name, team_tag, result)
        except Exception:
            logger.exception("예측 결과 저장 실패(predictions 테이블) - 응답에는 영향 없음")
        checkpoint("예측 결과 DB 저장 완료")

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
        logger.warning("[PREMIER 422] blue=%s#%s red=%s#%s error=%s", current.team_name, current.team_tag, team_name, team_tag, exc)
        checkpoint("요청 처리 실패: ValueError")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        checkpoint(f"요청 처리 실패: {type(exc).__name__}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        checkpoint("GET 예측 요청 처리 종료")
        logger.info("[PREDICTION REQUEST TIME] %.2fs", time.perf_counter() - started)
