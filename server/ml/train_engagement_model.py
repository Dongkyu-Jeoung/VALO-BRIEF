"""
교전 매치업 예측 - base 모델(트레이드 성공률/듀얼리스트 ACS 회귀) 학습 로직.

2026-09-11: trade_model/duelist_model을 따로(models/engagement_model.pkl) 저장하고
로지스틱 회귀 메타 모델을 별도로(models/engagement_meta_model.pkl) 저장하던 걸
합쳤다 - 두 파일을 따로 학습시키다 보니 base 모델만 재학습하고 메타 모델은 예전
버전인 채로 방치되는 등 버전이 어긋나는 사고가 실제로 있었다. 이제 이 모듈은
"base 모델을 계산만" 하고 파일 저장은 안 한다 - 저장은 ml/train_engagement_meta_model.py
(유일한 학습 진입점, `python -m ml.train_engagement_meta_model`)가 base+메타를
한 파일로 합쳐서 한다.

주의: team_engagement_cache에 실제로 쌓인 데이터가 MIN_SAMPLES 미만이면 학습을
거부하고 None을 반환한다 - 표본이 너무 적은 상태로 학습하면 과적합된 모델을
"진짜 학습된 모델"인 것처럼 배포하게 되는데, 이게 결정론적 통계(heuristic-v0)보다
못한 결과를 낼 수 있어 더 위험하다.
"""
from datetime import datetime, timezone

import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from database.connection import SessionLocal
from ml.engagement_training import FEATURE_COLUMNS, build_training_dataframe

MODEL_VERSION = "engagement-v2"

# ml/train_engagement_meta_model.py가 스태킹용 out-of-fold 예측을 만들 때 여기서 최종
# 배포되는 trade_model/duelist_model과 똑같은 하이퍼파라미터로 재현해야 하므로(다르면
# 메타 모델이 학습한 "base 모델의 특성"과 실제 배포된 base 모델의 특성이 어긋난다)
# 상수로 공유한다.
BASE_MODEL_PARAMS = dict(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)

# 표본이 이보다 적으면 학습을 거부한다 - 6개 피처짜리 회귀 모델이 train/test로 나눠도
# 최소한의 검증이 되려면 이 정도는 있어야 한다는 보수적인 최초 기준(정확한 최소치는
# 데이터가 쌓이는 대로 학습/검증 곡선을 보면서 재조정, 아직 확정된 값 아님).
MIN_SAMPLES = 60


def train_engagement_model(db=None, df: pd.DataFrame | None = None, min_samples: int = MIN_SAMPLES) -> dict | None:
    """base 모델(trade_model/duelist_model)을 학습만 하고 반환한다 - 파일에 저장하지
    않는다(저장은 호출부인 train_engagement_meta_model.py가 메타 모델과 합쳐서 한다).
    표본 부족이면 None.

    df를 이미 갖고 있으면(train_engagement_meta_model.py가 메타 학습용으로 이미 한 번
    만든 것) 그대로 재사용한다 - DB/API 왕복을 중복으로 만들지 않기 위함. df가 없으면
    직접 만든다(db를 안 넘기면 이 함수가 세션을 열고 닫음 - 단독 테스트/디버깅용)."""
    if df is None:
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
            "base 모델 학습을 건너뜁니다."
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

    # 베이스라인(항상 학습 데이터의 평균만 예측)과 비교 - 검증 없이 그냥 배포하는 상황을
    # 반복하지 않기 위해 최소한의 근거를 남긴다. train_engagement_meta_model.py가 이
    # 반환값의 "beats_baseline"을 보고 최종 artifact에 경고를 같이 남긴다.
    trade_baseline_pred = [y_trade_train.mean()] * len(y_trade_test)
    duelist_baseline_pred = [y_duelist_train.mean()] * len(y_duelist_test)

    trade_mae = mean_absolute_error(y_trade_test, trade_model.predict(X_test))
    trade_baseline_mae = mean_absolute_error(y_trade_test, trade_baseline_pred)
    duelist_mae = mean_absolute_error(y_duelist_test, duelist_model.predict(X_test))
    duelist_baseline_mae = mean_absolute_error(y_duelist_test, duelist_baseline_pred)

    print(f"[engagement] base 학습 샘플 {len(df)}건 (train {len(X_train)} / test {len(X_test)})")
    print(f"[engagement] 트레이드 성공률 MAE: 모델 {trade_mae:.2f} vs 베이스라인(평균) {trade_baseline_mae:.2f}")
    print(f"[engagement] 듀얼리스트 ACS MAE: 모델 {duelist_mae:.2f} vs 베이스라인(평균) {duelist_baseline_mae:.2f}")
    beats_baseline = trade_mae < trade_baseline_mae and duelist_mae < duelist_baseline_mae
    if not beats_baseline:
        print(
            "[engagement] 경고: base 모델이 단순 평균 베이스라인보다 안 나은 지표가 있습니다 - "
            "표본이 더 쌓이기 전까지는 참고용으로만 사용 권장."
        )

    return {
        "trade_model": trade_model,
        "duelist_model": duelist_model,
        "feature_columns": FEATURE_COLUMNS,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_samples": len(df),
        "beats_baseline": beats_baseline,
    }
