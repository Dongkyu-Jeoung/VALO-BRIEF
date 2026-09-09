from math import isfinite

import pandas as pd
from ml.model_loader import get_feature_columns

# Duelist Agent
DUELISTS = {
    "Jett",
    "Reyna",
    "Phoenix",
    "Neon",
    "Raze",
    "Yoru",
    "Iso",
    "Waylay"
}

NUMERIC_FEATURES = [
    "recent_acs",
    "recent_kd",
    "recent_kast",
    "recent_headshot_pct",
    "recent_winrate"
]


def validate_player_feature(feature):
    """DB/API/캐시가 동일한 수치 계약을 만족하는지 검사한다."""
    if not isinstance(feature, dict) or not isinstance(feature.get("agent"), str):
        raise ValueError("선수 피처 또는 요원 정보가 없습니다.")
    if not feature["agent"].strip() or feature["agent"] == "Unknown":
        raise ValueError("요원 정보가 없습니다.")
    for col in NUMERIC_FEATURES:
        try:
            value = float(feature[col])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"유효하지 않은 선수 피처: {col}") from exc
        maximum = 1 if col == "recent_winrate" else 100 if col in (
            "recent_kast", "recent_headshot_pct"
        ) else float("inf")
        if not isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f"선수 피처 범위 오류: {col}={value}")


def build_team_feature(blue_players, red_players):

    if len(blue_players) != 5 or len(red_players) != 5:
        raise ValueError("양 팀은 반드시 5명이어야 합니다.")

    for feature in [*blue_players, *red_players]:
        validate_player_feature(feature)

    row = {}

    for col in NUMERIC_FEATURES:

        blue_mean = sum(p[col] for p in blue_players) / 5
        red_mean = sum(p[col] for p in red_players) / 5

        row[f"blue_{col}"] = round(blue_mean, 2)
        row[f"red_{col}"] = round(red_mean, 2)
        row[f"diff_{col}"] = round(blue_mean - red_mean, 2)

    # Duelist 수
    blue_duel = sum(p["agent"] in DUELISTS for p in blue_players)
    red_duel = sum(p["agent"] in DUELISTS for p in red_players)

    row["blue_duelist_count"] = blue_duel
    row["red_duelist_count"] = red_duel
    row["diff_duelist_count"] = blue_duel - red_duel

    # 모델 학습 컬럼 순서 유지
    feature_order = get_feature_columns()

    return pd.DataFrame([row])[feature_order]
