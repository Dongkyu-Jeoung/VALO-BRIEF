import json
from pathlib import Path
from datetime import datetime
# 위 3개는 json 파일 저장할 때 쓰는 패키지
from model_loader import get_model
from rolling import build_player_feature
from team_feature import build_team_feature

model = get_model()


def predict_blue_win(blue_team, red_team, save_json=False):

    # 1. Rolling Feature 생성
    blue_players = [
        build_player_feature(p["name"], p["tag"])
        for p in blue_team
    ]

    red_players = [
        build_player_feature(p["name"], p["tag"])
        for p in red_team
    ]

    # 2. Team Feature 생성
    X = build_team_feature(
        blue_players,
        red_players
    )

    # 3. XGBoost 추론
    probability = float(
        model.predict_proba(X)[0][1]
    )

    winner = "BLUE" if probability >= 0.5 else "RED"

    # 4. 결과 반환
    result = {
        "blue_win_probability": round(probability * 100, 1),
        "predicted_winner": winner,

        "blue_summary": {
            "acs": round(X["blue_recent_acs"].iloc[0], 1),
            "kd": round(X["blue_recent_kd"].iloc[0], 2),
            "kast": round(X["blue_recent_kast"].iloc[0], 1),
            "winrate": round(X["blue_recent_winrate"].iloc[0] * 100, 1)
        },

        "red_summary": {
            "acs": round(X["red_recent_acs"].iloc[0], 1),
            "kd": round(X["red_recent_kd"].iloc[0], 2),
            "kast": round(X["red_recent_kast"].iloc[0], 1),
            "winrate": round(X["red_recent_winrate"].iloc[0] * 100, 1)
        }
    }

    # JSON 저장 (선택)
    if save_json:
        output_dir = Path("prediction_result")
        output_dir.mkdir(exist_ok=True)

        filename = datetime.now().strftime("%Y%m%d_%H%M%S_prediction.json")

        with open(
            output_dir / filename,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=4
            )

        print(f"JSON 저장 완료 : {output_dir / filename}")

    return result