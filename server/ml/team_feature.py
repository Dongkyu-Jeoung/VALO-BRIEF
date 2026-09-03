import pandas as pd
from model_loader import get_feature_columns

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


def build_team_feature(blue_players, red_players):

    if len(blue_players) != 5 or len(red_players) != 5:
        raise ValueError("양 팀은 반드시 5명이어야 합니다.")

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