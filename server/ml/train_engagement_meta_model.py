"""
교전 매치업 예측 - 통합 학습 스크립트(유일한 학습 진입점).

[인게임 데이터]   -> [Model 1: trade_model(XGB)]   -> P_trade(%) --┐
                                                                     +-> [Model 3: 메타 로지스틱 회귀] -> 최종 교전 승률(%)
[요원 상성 데이터] -> [Model 2: duelist_model(XGB)] -> P_match(%) --┘

2026-09-11: 원래 base 모델 2개(trade_model/duelist_model, models/engagement_model.pkl)와
메타 로지스틱 회귀(models/engagement_meta_model.pkl)를 따로 학습·저장했다. 따로 돌리다
보니 "base만 재학습하고 메타는 이전 버전 그대로 방치" 같은 버전 어긋남이 실제로
발생해서, **이 스크립트 하나가 base 학습(ml/train_engagement_model.py에 위임) -> 메타
학습 -> 하나의 파일(models/engagement_meta_model.pkl)로 합쳐 저장까지 전부 자동으로
한다.** 이제 models/engagement_model.pkl은 안 쓴다 - trade_model/duelist_model도
이 파일 안에 같이 들어있다.

핵심 설계 - 메타 학습용 P_trade/P_match를 왜 최종 배포될 base 모델로 안 뽑는가:
    최종 배포되는 trade_model/duelist_model은 "모든 학습 표본을 보고" 학습된다. 그
    모델로 같은 학습 표본에 대해 예측치(P_trade/P_match)를 뽑아 메타 모델의 입력으로
    쓰면, 메타 모델은 "base 모델이 학습 데이터를 얼마나 암기했는지"까지 같이
    학습해버려(누수) 실전(처음 보는 매치)에서는 안 맞는 과최적화된 가중치를 얻게
    된다. 그래서 K-Fold 교차검증으로 "그 표본을 학습에 안 쓴 fold의 모델"이 낸
    out-of-fold 예측치만 메타 학습에 쓴다(sklearn.model_selection.cross_val_predict) -
    실제 배포되는 base 모델은 전체 데이터로 별도로 다시 학습해서 같은 artifact에 넣는다.

실행(direct DB):
    python -m ml.train_engagement_meta_model
실행(API 경유 - DB에 직접 못 붙는 환경):
    python -m ml.train_engagement_meta_model --api-url http://localhost:8000
    (routers/ml.py::GET /api/ml/engagement-training-data를 호출해서 학습 데이터를 받아온다)

저장 규칙: base 모델(MIN_SAMPLES=60, ml/train_engagement_model.py)이 학습 안 되면
(표본 부족) 아무 파일도 안 남긴다. base는 학습됐는데 메타(label_win 있는 표본이
META_MIN_SAMPLES=40 미만)만 표본이 부족하면, base만 담은 artifact를 저장하고
meta_model은 None으로 둔다 - ml/engagement_predictor.py가 이 경우 finalPrediction
없이 trade/duelistMatchup까지만 내려주는 것으로 자동 폴백한다(교전매치업_예측_분석.md
8/9번 참고).
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
from ml.train_engagement_model import BASE_MODEL_PARAMS, train_engagement_model

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "engagement_meta_model.pkl"
MODEL_VERSION = "engagement-meta-v2"
META_FEATURE_COLUMNS = ["p_trade", "p_match"]

# label_win이 있는(=매치 결과를 아는) 표본이 이보다 적으면 메타 단계를 건너뛴다. 피처가
# 2개뿐인 가벼운 로지스틱 회귀라 base 모델(MIN_SAMPLES=60)보다는 덜 보수적으로 잡았다 -
# 정확한 최소치는 아니고, 데이터가 쌓이면 재조정 대상.
META_MIN_SAMPLES = 40
N_FOLDS = 5


def _fetch_training_dataframe_via_api(api_url: str) -> pd.DataFrame:
    """DB에 직접 못 붙는 환경(다른 머신 등)용 대체 경로 - routers/ml.py::GET /api/ml/
    engagement-training-data가 build_training_dataframe(db)를 그대로 반환한다."""
    res = httpx.get(f"{api_url.rstrip('/')}/api/ml/engagement-training-data", timeout=30.0)
    res.raise_for_status()
    payload = res.json()
    return pd.DataFrame(payload["rows"], columns=FEATURE_COLUMNS + LABEL_COLUMNS + META_COLUMNS)


def _out_of_fold_meta_features(df: pd.DataFrame) -> pd.DataFrame:
    """df 전체(누수 방지를 위해 label_win 유무와 무관하게 전체 표본)에 대해 K-Fold
    out-of-fold P_trade/P_match를 만든다. 최종 배포될 base 모델과 정확히 같은
    하이퍼파라미터(BASE_MODEL_PARAMS)로, 매 fold마다 새로 학습한 모델을 쓴다 - 모듈
    docstring "핵심 설계" 참고."""
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


def _train_meta_stage(df: pd.DataFrame, min_samples: int) -> dict | None:
    """메타 로지스틱 회귀만 학습(out-of-fold 피처 생성 포함). 표본 부족이면 None -
    이 경우 base 모델만 담긴 artifact가 저장된다(모듈 docstring 저장 규칙 참고)."""
    meta_features = _out_of_fold_meta_features(df)
    full = pd.concat([df[["label_win"]], meta_features], axis=1).dropna(subset=["label_win"])

    if len(full) < min_samples:
        print(
            f"[engagement-meta] 승패를 아는 학습 표본이 부족합니다 ({len(full)}건, 최소 "
            f"{min_samples}건 필요) - 메타 단계를 건너뜁니다. finalPrediction 없이 "
            "trade/duelistMatchup만 계속 쓰입니다."
        )
        return None

    X = full[META_FEATURE_COLUMNS]
    y = full["label_win"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    meta_model = LogisticRegression()
    meta_model.fit(X_train, y_train)

    # 베이스라인(항상 학습 데이터의 다수 클래스만 예측) 대비 - 최소한의 검증 근거를 남긴다.
    majority_class = y_train.mode()[0]
    baseline_pred = np.full(len(y_test), majority_class)
    baseline_acc = accuracy_score(y_test, baseline_pred)

    pred_proba = meta_model.predict_proba(X_test)[:, 1]
    pred_label = (pred_proba >= 0.5).astype(int)
    model_acc = accuracy_score(y_test, pred_label)

    print(f"[engagement-meta] 메타 학습 샘플 {len(full)}건 (train {len(X_train)} / test {len(X_test)})")
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
    beats_baseline = model_acc > baseline_acc
    if not beats_baseline:
        print(
            "[engagement-meta] 경고: 메타 모델이 다수 클래스 베이스라인보다 안 나음 - "
            "표본이 더 쌓이기 전까지는 신뢰도에 주의(finalPrediction은 참고용으로만 사용 권장)."
        )

    # 어느 피처에 얼마나 가중치를 뒀는지 - LogisticRegression 계수는 "그 피처가 1 커질 때
    # 로그오즈가 얼마나 변하는지"라서 부호/크기로 방향과 상대적 크기를 바로 읽을 수 있다.
    coef = dict(zip(META_FEATURE_COLUMNS, meta_model.coef_[0]))
    total_abs = sum(abs(v) for v in coef.values()) or 1.0
    print("[engagement-meta] 학습된 가중치(로지스틱 회귀 계수, 절대값 기준 상대 비중):")
    for name, value in sorted(coef.items(), key=lambda kv: -abs(kv[1])):
        print(f"    {name}: {value:+.4f} (상대 비중 {abs(value) / total_abs:.1%})")

    # 전체 표본으로 다시 학습해서 배포 - train/test 분리는 위 검증용, 실제 배포 모델은
    # 가진 데이터를 최대한 다 쓴다.
    meta_model_final = LogisticRegression()
    meta_model_final.fit(X, y)

    return {
        "meta_model": meta_model_final,
        "meta_feature_columns": META_FEATURE_COLUMNS,
        "meta_training_samples": len(full),
        "meta_beats_baseline": beats_baseline,
    }


def train_engagement_meta_model(db=None, api_url: str | None = None) -> dict | None:
    """base 모델(trade_model/duelist_model) 학습 -> 메타 로지스틱 회귀 학습 -> 하나의
    artifact로 합쳐 models/engagement_meta_model.pkl에 저장까지 전부 한다(유일한 학습
    진입점). base가 표본 부족으로 실패하면 아무것도 저장하지 않고 None을 반환한다."""
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

    base_result = train_engagement_model(df=df)
    if base_result is None:
        print("[engagement-meta] base 모델 학습에 실패해 아무 파일도 저장하지 않습니다.")
        return None

    meta_result = _train_meta_stage(df, META_MIN_SAMPLES)

    artifact = {
        "trade_model": base_result["trade_model"],
        "duelist_model": base_result["duelist_model"],
        "feature_columns": base_result["feature_columns"],
        "base_training_samples": base_result["training_samples"],
        "base_beats_baseline": base_result["beats_baseline"],
        "meta_model": meta_result["meta_model"] if meta_result else None,
        "meta_feature_columns": META_FEATURE_COLUMNS,
        "meta_training_samples": meta_result["meta_training_samples"] if meta_result else 0,
        "meta_beats_baseline": meta_result["meta_beats_baseline"] if meta_result else None,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    print(f"[engagement-meta] 저장 완료(base{'+ meta' if meta_result else ' only'}): {MODEL_PATH}")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="교전 매치업 예측 base+메타 모델 통합 학습")
    parser.add_argument(
        "--api-url", default=None,
        help="지정하면 DB에 직접 안 붙고 이 주소의 /api/ml/engagement-training-data로 학습 데이터를 받아온다(예: http://localhost:8000)",
    )
    args = parser.parse_args()
    train_engagement_meta_model(api_url=args.api_url)
