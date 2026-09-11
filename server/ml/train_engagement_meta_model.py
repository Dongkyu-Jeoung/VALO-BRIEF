"""
교전 매치업 예측 - 스태킹 메타 모델 학습 스크립트.

[인게임 데이터] -> [trade_model(XGB)] -> P_trade(%) --┐
                                                        +-> [메타 로지스틱 회귀] -> 최종 교전 승률(%)
[요원 상성 데이터] -> [duelist_model(XGB)] -> P_match(%) --┘

ml/train_engagement_model.py가 만든 base 모델 2개(trade_model/duelist_model, models/
engagement_model.pkl)의 예측치를 "메타 피처" 2개(P_trade/P_match)로 놓고, 실제 매치
승패(label_win)를 라벨로 삼아 가벼운 로지스틱 회귀 하나를 더 학습한다. 두 base 모델
출력에 얼마나 가중치를 줄지(예: 트레이드가 결정적인 상황 vs 듀얼리스트 매치업이
결정적인 상황)를 하드코딩하지 않고 데이터로부터 직접 학습하는 게 목적 - VALO-BRIEF
루트의 교전매치업_예측_분석.md 8번 참고.

핵심 설계 - 왜 base 모델을 그대로 재사용하지 않고 여기서 K-Fold로 다시 학습하는가:
    models/engagement_model.pkl에 이미 저장된 trade_model/duelist_model은 "모든 학습
    표본을 보고" 학습됐다. 그 모델로 같은 학습 표본에 대해 예측치(P_trade/P_match)를
    뽑아 메타 모델의 입력으로 쓰면, 메타 모델은 "base 모델이 학습 데이터를 얼마나
    암기했는지"까지 같이 학습해버려(누수) 실전(처음 보는 매치)에서는 안 맞는 과최적화된
    가중치를 얻게 된다. 그래서 K-Fold 교차검증으로 "그 표본을 학습에 안 쓴 fold의
    모델"이 낸 out-of-fold 예측치만 메타 학습에 쓴다(sklearn.model_selection.
    cross_val_predict) - 실제 배포되는 base 모델(engagement_model.pkl)은 그대로 두고,
    메타 학습용 예측치만 별도로 정직하게 다시 만드는 것.

실행(direct DB):
    python -m ml.train_engagement_meta_model
실행(API 경유, ml/train_engagement_model.py와 동일한 이유/방식):
    python -m ml.train_engagement_meta_model --api-url http://localhost:8000

주의: label_win(실제 매치 승패)이 있는 표본이 META_MIN_SAMPLES 미만이면 학습을 거부하고
아무 파일도 안 남긴다(ml/train_engagement_model.py의 MIN_SAMPLES 가드와 같은 이유) -
이 경우 ml/engagement_predictor.py는 finalPrediction 없이 기존 trade/duelistMatchup만
내려주는 것으로 자동 폴백한다(하위 호환).
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import KFold, cross_val_predict, train_test_split
from xgboost import XGBRegressor

from database.connection import SessionLocal
from ml.engagement_predictor import normalize_to_100
from ml.engagement_training import FEATURE_COLUMNS, LABEL_COLUMNS, META_COLUMNS, build_training_dataframe
from ml.train_engagement_model import BASE_MODEL_PARAMS

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "engagement_meta_model.pkl"
MODEL_VERSION = "engagement-meta-v1"
META_FEATURE_COLUMNS = ["p_trade", "p_match"]

# label_win이 있는(=매치 결과를 아는) 표본이 이보다 적으면 학습을 거부한다. 피처가 2개뿐인
# 가벼운 로지스틱 회귀라 base 모델(MIN_SAMPLES=60)보다는 덜 보수적으로 잡았다 - 정확한
# 최소치는 아니고, 데이터가 쌓이면 재조정 대상(ml/train_engagement_model.py와 동일한 톤).
META_MIN_SAMPLES = 40
N_FOLDS = 5


def _fetch_training_dataframe_via_api(api_url: str) -> pd.DataFrame:
    """ml/train_engagement_model.py의 동명 함수와 동일한 이유(직접 DB 접근이 안 되는
    환경) - 다만 label_win 계산에 필요한 META_COLUMNS까지 같이 복원해야 한다."""
    res = httpx.get(f"{api_url.rstrip('/')}/api/ml/engagement-training-data", timeout=30.0)
    res.raise_for_status()
    payload = res.json()
    return pd.DataFrame(payload["rows"], columns=FEATURE_COLUMNS + LABEL_COLUMNS + META_COLUMNS)


def _out_of_fold_meta_features(df: pd.DataFrame) -> pd.DataFrame:
    """df 전체(누수 방지를 위해 label_win 유무와 무관하게 전체 표본)에 대해 K-Fold
    out-of-fold P_trade/P_match를 만든다. base 모델과 정확히 같은 하이퍼파라미터
    (BASE_MODEL_PARAMS)로, 매 fold마다 새로 학습한 모델을 쓴다 - 모듈 docstring
    "핵심 설계" 참고."""
    X = df[FEATURE_COLUMNS]
    y_trade = df["label_trade_rate"]
    y_duelist = df["label_duelist_acs"]

    n_splits = min(N_FOLDS, len(df))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    oof_trade = cross_val_predict(XGBRegressor(**BASE_MODEL_PARAMS), X, y_trade, cv=kf)
    oof_duelist = cross_val_predict(XGBRegressor(**BASE_MODEL_PARAMS), X, y_duelist, cv=kf)

    p_trade = np.clip(oof_trade, 0.0, 100.0)
    oof_duelist_clipped = np.clip(oof_duelist, 0.0, None)
    # p_match = "우리팀 예측 듀얼리스트 ACS" vs "상대팀 실측(=피처로 들어간) 듀얼리스트
    # ACS"를 0~100으로 정규화한 점수 - 라이브 추론(_predict_with_model이 duelistMatchup을
    # 만들 때 쓰는 것)과 완전히 같은 식(normalize_to_100)을 그대로 재사용해서 학습/추론
    # 피처가 어긋나지 않게 한다.
    p_match = np.array([
        normalize_to_100(our, opp)[0]
        for our, opp in zip(oof_duelist_clipped, df["opponent_recent_duelist_acs"])
    ])

    return pd.DataFrame({"p_trade": p_trade, "p_match": p_match}, index=df.index)


def train_engagement_meta_model(db=None, min_samples: int = META_MIN_SAMPLES, api_url: str | None = None) -> dict | None:
    """학습 후 저장한 메타 모델 아티팩트(dict)를 반환. 표본 부족이면 None(파일 안 건드림) -
    ml/train_engagement_model.py::train_engagement_model과 동일한 계약."""
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

    meta_features = _out_of_fold_meta_features(df)
    full = pd.concat([df[["label_win"]], meta_features], axis=1).dropna(subset=["label_win"])

    if len(full) < min_samples:
        print(
            f"[engagement-meta] 승패를 아는 학습 표본이 부족합니다 ({len(full)}건, 최소 "
            f"{min_samples}건 필요) - 학습을 건너뜁니다. finalPrediction 없이 기존 trade/"
            "duelistMatchup만 계속 쓰입니다."
        )
        return None

    X = full[META_FEATURE_COLUMNS]
    y = full["label_win"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    meta_model = LogisticRegression()
    meta_model.fit(X_train, y_train)

    # 베이스라인(항상 학습 데이터의 다수 클래스만 예측) 대비 - ml/train_engagement_model.py와
    # 같은 이유로 최소한의 검증 근거를 남긴다.
    majority_class = y_train.mode()[0]
    baseline_pred = np.full(len(y_test), majority_class)
    baseline_acc = accuracy_score(y_test, baseline_pred)

    pred_proba = meta_model.predict_proba(X_test)[:, 1]
    pred_label = (pred_proba >= 0.5).astype(int)
    model_acc = accuracy_score(y_test, pred_label)

    print(f"[engagement-meta] 학습 샘플 {len(full)}건 (train {len(X_train)} / test {len(X_test)})")
    print(f"[engagement-meta] 정확도: 메타 모델 {model_acc:.2%} vs 베이스라인(다수 클래스) {baseline_acc:.2%}")
    if y_test.nunique() > 1:
        try:
            baseline_proba = np.full(len(y_test), y_train.mean())
            print(
                f"[engagement-meta] Log Loss: 메타 모델 {log_loss(y_test, pred_proba):.3f} "
                f"vs 베이스라인(평균) {log_loss(y_test, baseline_proba):.3f}"
            )
        except ValueError:
            pass
    if model_acc <= baseline_acc:
        print(
            "[engagement-meta] 경고: 메타 모델이 다수 클래스 베이스라인보다 안 나음 - "
            "표본이 더 쌓이기 전까지는 신뢰도에 주의(finalPrediction은 참고용으로만 사용 권장)."
        )

    # 실제로 P_trade/P_match 중 어느 쪽에 더 가중치를 뒀는지 - LogisticRegression 계수는
    # "그 피처가 1 커질 때 로그오즈가 얼마나 변하는지"라서 부호/크기로 방향과 상대적 크기를
    # 바로 읽을 수 있다(요청하신 "가중치" 그 자체).
    coef = dict(zip(META_FEATURE_COLUMNS, meta_model.coef_[0]))
    total_abs = sum(abs(v) for v in coef.values()) or 1.0
    print("[engagement-meta] 학습된 가중치(로지스틱 회귀 계수, 절대값 기준 상대 비중):")
    for name, value in sorted(coef.items(), key=lambda kv: -abs(kv[1])):
        print(f"    {name}: {value:+.4f} (상대 비중 {abs(value) / total_abs:.1%})")

    # 전체 표본으로 다시 학습해서 배포 - train/test 분리는 위 검증용, 실제 배포 모델은
    # 가진 데이터를 최대한 다 쓴다(ml/train_engagement_model.py와 동일한 관례).
    meta_model_final = LogisticRegression()
    meta_model_final.fit(X, y)

    artifact = {
        "meta_model": meta_model_final,
        "feature_columns": META_FEATURE_COLUMNS,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_samples": len(full),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    print(f"[engagement-meta] 저장 완료: {MODEL_PATH}")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="교전 매치업 예측 스태킹 메타 모델 학습")
    parser.add_argument(
        "--api-url", default=None,
        help="지정하면 DB에 직접 안 붙고 이 주소의 /api/ml/engagement-training-data로 학습 데이터를 받아온다(예: http://localhost:8000)",
    )
    args = parser.parse_args()
    train_engagement_meta_model(api_url=args.api_url)
