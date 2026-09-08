import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
# 위 3개는 json 파일 저장할 때 쓰는 패키지
from ml.model_loader import get_model
from ml.rolling import build_player_feature, resolve_puuid
from ml.team_feature import build_team_feature

model = get_model()

def predict_blue_win(blue_team, red_team, save_json=False, db=None):

    all_team = blue_team + red_team  # 앞 5명 blue, 뒤 5명 red 순서 고정

    # 1. puuid 선확인 - SQLAlchemy Session은 스레드-세이프하지 않으므로, db를 쓰는 이
    # 단계는 아래 병렬 구간 진입 전에 순차로 다 끝내둔다(db 캐시 히트면 빠른 쿼리, 미스면
    # Henrik 요청 1건 - 승부예측_성능_분석.md 5-1/5-4번). 여기서 못 찾으면 병렬 구간에
    # 들어가지도 않고 바로 실패시킨다(기존 build_player_feature의 실패 메시지와 동일).
    puuids = []
    for p in all_team:
        puuid = resolve_puuid(p["name"], p["tag"], db)
        if puuid is None:
            raise ValueError(f"{p['name']}#{p['tag']} PUUID 조회 실패")
        puuids.append(puuid)

    # 2. Rolling Feature 생성 - puuid가 이미 다 정해졌으니 이 구간은 db를 안 쓴다.
    # 선수 10명을 동시에 처리해서(ThreadPoolExecutor) 예전에 순차 호출 때 선수마다 그대로
    # 쌓이던 네트워크 왕복 지연을 없앤다. 실제 Henrik 요청 상한(분당 28건, services/
    # rate_limiter.py)은 병렬로 돌려도 그대로 지켜지므로 총 소요시간의 하한 자체가 줄지는
    # 않는다(승부예측_성능_분석.md 5-4번 참고) - 그 하한 안에서 낭비되던 시간만 없앤다.
    with ThreadPoolExecutor(max_workers=len(all_team)) as executor:
        all_players = list(executor.map(
            lambda args: build_player_feature(args[0]["name"], args[0]["tag"], puuid=args[1]),
            zip(all_team, puuids),
        ))

    blue_players = all_players[:len(blue_team)]
    red_players = all_players[len(blue_team):]

    # 3. Team Feature 생성
    X = build_team_feature(
        blue_players,
        red_players
    )

    # 4. XGBoost 추론
    probability = float(
        model.predict_proba(X)[0][1]
    )

    winner = "BLUE" if probability >= 0.5 else "RED"

    # 5. 결과 반환
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