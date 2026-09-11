"""
교전 매치업 예측 모델(트레이드 성공률/듀얼리스트 ACS) 학습 스크립트.
server/승부예측_성능_분석.md 7-4번 참고 - 메인 승률 모델(models/xgboost_valorant.pkl)과
달리 이건 이 저장소 안에 학습 스크립트가 존재하는 첫 모델이다(4-1번에서 지적한 "학습
스크립트가 아예 없어서 검증도 재학습도 불가능"한 상황을 반복하지 않기 위해 처음부터
train/test 분리 + 베이스라인 비교를 포함해서 만듦).

실행(direct DB - 서버와 같은 환경/DB 접근 권한이 있을 때):
    python -m ml.train_engagement_model

실행(API 경유 - DB에 직접 못 붙는 환경, 예: 다른 머신/노트북. server/승부예측_성능_분석.md
"학습은 데이터를 api를 통해 가져와야 할거같아" 요청 반영):
    python -m ml.train_engagement_model --api-url http://localhost:8000
    (routers/ml.py::GET /api/ml/engagement-training-data를 호출해서 학습 데이터를 받아온다)

주의: team_engagement_cache에 실제로 쌓인 데이터가 MIN_SAMPLES 미만이면 학습을
거부하고 아무 파일도 안 남긴다 - 표본이 너무 적은 상태로 학습하면 과적합된 모델을
"진짜 학습된 모델"인 것처럼 배포하게 되는데, 이게 결정론적 통계(heuristic-v0)보다
못한 결과를 낼 수 있어 더 위험하다(server/승부예측_성능_분석.md 7-2번 - 애초에 데이터가
쌓여야 하는 이유).
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from database.connection import SessionLocal
from ml.engagement_training import FEATURE_COLUMNS, LABEL_COLUMNS, build_training_dataframe

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "engagement_model.pkl"
MODEL_VERSION = "engagement-v1"

# ml/train_engagement_meta_model.py가 스태킹용 out-of-fold 예측을 만들 때 여기 배포되는
# trade_model/duelist_model과 똑같은 하이퍼파라미터로 재현해야 하므로(다르면 메타 모델이
# 학습한 "base 모델의 특성"과 실제 배포된 base 모델의 특성이 어긋난다) 상수로 공유한다.
BASE_MODEL_PARAMS = dict(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)

# 표본이 이보다 적으면 학습을 거부한다 - 6개 피처짜리 회귀 모델이 train/test로 나눠도
# 최소한의 검증이 되려면 이 정도는 있어야 한다는 보수적인 최초 기준(정확한 최소치는
# 데이터가 쌓이는 대로 학습/검증 곡선을 보면서 재조정 - server/승부예측_성능_분석.md
# 7-2번 참고, 아직 확정된 값 아님).
MIN_SAMPLES = 60


def _fetch_training_dataframe_via_api(api_url: str) -> pd.DataFrame:
    """routers/ml.py::GET /api/ml/engagement-training-data 호출로 학습 데이터를 받아온다.
    build_training_dataframe(db)를 직접 부르는 것과 결과가 같다(같은 함수를 서버가
    호출해서 그대로 반환) - DB 세션을 못 여는 환경에서 쓰는 대체 경로."""
    res = httpx.get(f"{api_url.rstrip('/')}/api/ml/engagement-training-data", timeout=30.0)
    res.raise_for_status()
    payload = res.json()
    return pd.DataFrame(payload["rows"], columns=FEATURE_COLUMNS + LABEL_COLUMNS)


def train_engagement_model(db=None, min_samples: int = MIN_SAMPLES, api_url: str | None = None) -> dict | None:
    """학습 후 저장한 아티팩트(dict)를 반환. 표본 부족 등으로 학습을 안 했으면 None -
    이 경우 models/engagement_model.pkl은 건드리지 않는다(기존 파일이 있으면 그대로 둠).

    api_url이 주어지면 DB에 직접 안 붙고 HTTP로 학습 데이터를 받아온다(위 모듈 docstring
    참고). 안 주면 기존처럼 direct DB 경로 - db를 안 넘기면 이 함수가 직접 세션을 열고
    닫는다(CLI 실행용), 테스트 코드는 스크래치 세션을 직접 넘겨서 커밋 시점을 제어할 수
    있다."""
    if api_url:
        df = _fetch_training_dataframe_via_api(api_url)
    else:
        owns_session = db is None
        if owns_session:
            db = SessionLocal()
        try:
            df = build_training_dataframe(db)
        finally:
            if owns_session:
                db.close()

    if len(df) < min_samples:
        print(
            f"[engagement] 학습 데이터가 부족합니다 ({len(df)}건, 최소 {min_samples}건 필요) - "
            "학습을 건너뜁니다. server/승부예측_성능_분석.md 7-2번(데이터 축적) 참고."
        )
        return None

    X = df[FEATURE_COLUMNS]
    y_trade = df["label_trade_rate"]
    y_duelist = df["label_duelist_acs"]

    X_train, X_test, y_trade_train, y_trade_test, y_duelist_train, y_duelist_test = train_test_split(
        X, y_trade, y_duelist, test_size=0.2, random_state=42
    )

    trade_model = XGBRegressor(**BASE_MODEL_PARAMS)
    trade_model.fit(X_train, y_trade_train)

    duelist_model = XGBRegressor(**BASE_MODEL_PARAMS)
    duelist_model.fit(X_train, y_duelist_train)

    # 베이스라인(항상 학습 데이터의 평균만 예측)과 비교 - 4번에서 지적한 "검증 없이 그냥
    # 배포"하는 상황을 반복하지 않기 위해 최소한의 근거를 남긴다.
    trade_baseline_pred = [y_trade_train.mean()] * len(y_trade_test)
    duelist_baseline_pred = [y_duelist_train.mean()] * len(y_duelist_test)

    trade_mae = mean_absolute_error(y_trade_test, trade_model.predict(X_test))
    trade_baseline_mae = mean_absolute_error(y_trade_test, trade_baseline_pred)
    duelist_mae = mean_absolute_error(y_duelist_test, duelist_model.predict(X_test))
    duelist_baseline_mae = mean_absolute_error(y_duelist_test, duelist_baseline_pred)

    print(f"[engagement] 학습 샘플 {len(df)}건 (train {len(X_train)} / test {len(X_test)})")
    print(f"[engagement] 트레이드 성공률 MAE: 모델 {trade_mae:.2f} vs 베이스라인(평균) {trade_baseline_mae:.2f}")
    print(f"[engagement] 듀얼리스트 ACS MAE: 모델 {duelist_mae:.2f} vs 베이스라인(평균) {duelist_baseline_mae:.2f}")
    if trade_mae >= trade_baseline_mae or duelist_mae >= duelist_baseline_mae:
        print(
            "[engagement] 경고: 모델이 단순 평균 베이스라인보다 안 나은 지표가 있습니다 - "
            "표본이 더 쌓이기 전까지는 heuristic-v0(결정론적 통계) 유지를 권장합니다."
        )

    artifact = {
        "trade_model": trade_model,
        "duelist_model": duelist_model,
        "feature_columns": FEATURE_COLUMNS,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_samples": len(df),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    print(f"[engagement] 저장 완료: {MODEL_PATH}")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="교전 매치업 예측 모델 학습")
    parser.add_argument(
        "--api-url", default=None,
        help="지정하면 DB에 직접 안 붙고 이 주소의 /api/ml/engagement-training-data로 학습 데이터를 받아온다(예: http://localhost:8000)",
    )
    args = parser.parse_args()
    train_engagement_model(api_url=args.api_url)
