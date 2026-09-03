from pathlib import Path
import joblib

# model_loader.py 위치 기준
BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = BASE_DIR / "models" / "xgboost_valorant.pkl"
FEATURE_PATH = BASE_DIR / "models" / "feature_columns.pkl"

# 서버 시작 시 1회 로드
model = joblib.load(MODEL_PATH)
feature_columns = joblib.load(FEATURE_PATH)


def get_model():
    return model


def get_feature_columns():
    return feature_columns