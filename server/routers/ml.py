"""
ML 학습 파이프라인 지원 엔드포인트. server/승부예측_성능_분석.md 9번 참고.

ml/train_engagement_model.py가 DB 세션을 직접 열 수 없는 환경(다른 머신, 노트북 등)에서도
학습 데이터를 받아올 수 있도록 team_engagement_cache 기반 학습 DataFrame을 HTTP로
노출한다 - 서버와 같은 프로세스에서 돌릴 때 쓰는 기존 direct-DB 경로도 그대로 남아있다
(train_engagement_model(db=...)).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.connection import get_db
from ml.engagement_training import build_training_dataframe

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/engagement-training-data")
def get_engagement_training_data(db: Session = Depends(get_db)):
    """ml/train_engagement_model.py가 --api-url 모드에서 호출. FEATURE_COLUMNS +
    LABEL_COLUMNS를 가진 행(row) 리스트를 그대로 반환 - pandas.DataFrame(rows)로 바로
    복원 가능한 shape(NaN은 JSON에서 null로 내려가므로 학습 스크립트가 dropna로 방어)."""
    df = build_training_dataframe(db)
    return {"rows": df.to_dict(orient="records"), "count": len(df)}
