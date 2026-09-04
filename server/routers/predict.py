from fastapi import APIRouter, HTTPException

from schema.predict import (
    PredictRequest,
    PredictResponse
)

from ml.predictor import predict_blue_win

router = APIRouter(
    prefix="/predict",
    tags=["Predict"]
)


@router.post(
    "",
    response_model=PredictResponse
)
def predict(request: PredictRequest):

    try:

        result = predict_blue_win(
            blue_team=[
                p.model_dump()
                for p in request.blue_team
            ],
            red_team=[
                p.model_dump()
                for p in request.red_team
            ]
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )