"""
승부 예측 (Frame 07, 08). 엔드포인트 두 개로 나뉜다.

- POST /api/predict: ml 파이프라인 자체를 테스트하기 위한 저수준 엔드포인트(5v5 로스터를
  직접 입력받음) - 화면에서 선수 10명을 직접 타이핑하게 할 수 없어서 프론트는 이걸 쓰지
  않는다(ML 개발/디버깅용으로 남겨둠). DB 저장 없음.
- GET /api/predict/{team_name}/{team_tag}: 프론트(MatchPredictionPage, api/prediction.js)가
  실제로 호출하는 엔드포인트. 로그인한 팀(JWT) vs URL의 상대팀 로스터를 Henrik에서 자동으로
  찾아 같은 파이프라인에 넣고, 결과를 predictions 테이블에 저장한다.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.connection import get_db
from ml.predictor import predict_blue_win
from models.team import Team
from routers.auth import get_current_team
from schema.predict import PredictRequest, PredictResponse
from services import predict_service
from services.henrik_api import HenrikRateLimitError

router = APIRouter(prefix="/api/predict", tags=["Predict"])

MODEL_VERSION = "xgboost-v1"


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
        # main.py의 전역 핸들러가 503 + 안내 메시지로 응답하게 그대로 올려보낸다 -
        # 아래 except Exception으로 잡으면 "존재하지 않음"과 구분 안 되는 500이 된다.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-opponent")
async def get_recent_opponent(current: Team = Depends(get_current_team)):
    """로그인한 팀의 가장 최근 프리미어 매치 상대팀을 찾는다. 승부예측 페이지가 로그인
    상태일 때 데모용 상대팀(team-ascend) 대신 이 팀을 자동으로 상대팀으로 쓴다."""
    opponent = await predict_service.resolve_recent_opponent(current.team_name, current.team_tag)
    if opponent is None:
        raise HTTPException(status_code=404, detail="최근 매치 상대팀을 찾을 수 없습니다.")
    return opponent


@router.get("/{team_name}/{team_tag}")
async def predict_match(
    team_name: str,
    team_tag: str,
    current: Team = Depends(get_current_team),
    db: Session = Depends(get_db),
):
    """로그인한 팀(우리팀) vs URL의 상대팀을 예측. 두 팀 각각 최근 매치의 5인 로스터를
    Henrik에서 찾아(services/predict_service.resolve_recent_roster) 기존 XGBoost
    파이프라인에 넣고, 결과를 predictions 테이블에 저장한 뒤 승률만 반환한다(맵별 상세
    분석/AI 리포트는 모델이 아직 만들지 않는 데이터라 이 응답엔 없음 - 프론트가 그 부분은
    당분간 mock으로 채운다, api/prediction.js 참고)."""
    (our_info, our_roster), (opp_info, opp_roster) = await asyncio.gather(
        predict_service.resolve_recent_roster(current.team_name, current.team_tag),
        predict_service.resolve_recent_roster(team_name, team_tag),
    )

    if opp_info is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 프리미어 팀입니다.")
    if len(our_roster) != 5 or len(opp_roster) != 5:
        raise HTTPException(
            status_code=422,
            detail="최근 매치의 5인 로스터를 찾지 못해 예측할 수 없습니다.",
        )

    # ml/valorant_git.py가 동기 requests 기반이라(await 불가), 이벤트 루프를 막지 않도록
    # 별도 스레드에서 돌린다 - 안 그러면 이 예측이 끝날 때까지 서버 전체가 멈춘다.
    # db를 같이 넘기면 build_player_feature가 riot_accounts에 이미 캐싱된 puuid를 재사용해
    # 선수당 Henrik 요청을 최대 1건 아낀다(이 시점엔 위 두 resolve_recent_roster 호출이
    # 이미 끝나 db가 쓰이고 있지 않으니 스레드로 넘겨도 안전 - 아래 save_prediction에서만
    # 다시 쓰인다).
    try:
        result = await asyncio.to_thread(predict_blue_win, our_roster, opp_roster, db=db)
    except HenrikRateLimitError:
        # main.py의 전역 핸들러가 503 + 안내 메시지로 응답하게 그대로 올려보낸다 -
        # 아래 except Exception으로 잡으면 "존재하지 않음"과 구분 안 되는 500이 된다.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    predict_service.save_prediction(
        db,
        team_a_id=current.team_id,
        opponent_team_name=team_name,
        opponent_team_tag=team_tag,
        predicted_winrate_a=result["blue_win_probability"],
        predicted_winrate_b=round(100 - result["blue_win_probability"], 1),
        model_version=MODEL_VERSION,
        feature_snapshot={"blue_summary": result["blue_summary"], "red_summary": result["red_summary"]},
    )

    our_logo = ((our_info or {}).get("customization") or {}).get("image")
    opp_logo = (opp_info.get("customization") or {}).get("image")

    return {
        "ourTeam": {
            "name": current.team_name,
            "tag": current.team_tag,
            "avgWinRate20": result["blue_summary"]["winrate"],
            "logoUrl": our_logo,
        },
        "opponentTeam": {
            "name": opp_info.get("name") or team_name,
            "tag": opp_info.get("tag") or team_tag,
            "avgWinRate20": result["red_summary"]["winrate"],
            "logoUrl": opp_logo,
        },
        "ourWinChance": result["blue_win_probability"],
    }
