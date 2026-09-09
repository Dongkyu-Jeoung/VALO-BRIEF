import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from uuid import uuid4
# 위 3개는 json 파일 저장할 때 쓰는 패키지
import time
from ml.model_loader import get_model
from ml.rolling import (
    build_player_feature,
    get_cached_player_feature,
    resolve_puuid,
    save_player_feature_cache,
)
from ml.team_feature import build_team_feature, validate_player_feature
from ml.db_rolling import (
    load_recent_matches,
    add_match_side,
    add_win_column,
    build_db_player_feature,
)

model = get_model()


def create_prediction_checkpoint():
    """동시 요청을 구분하고, 로스터 조회부터 같은 기준으로 시간을 기록한다."""
    started = time.perf_counter()
    request_id = uuid4().hex[:8]

    def checkpoint(label):
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        elapsed = time.perf_counter() - started
        print(f"[{timestamp}] [predict={request_id}] [+{elapsed:.3f}s] {label}", flush=True)

    return checkpoint

def _db_player_feature(db, puuid, checkpoint=None, player_label="BLUE"):
    def report(reason):
        if checkpoint is not None:
            checkpoint(f"[DB REJECT] {player_label} puuid={puuid[:8]}... {reason}")

    if db is None:
        report("DB_UNAVAILABLE: DB 세션 없음")
        return None
    # SQL/연결 장애는 숨기지 않는다. 데이터 불완전만 fallback한다.
    df = load_recent_matches(db, puuid)
    if df is None or df.empty:
        report("NO_VALID_MATCHES: DB에서 조건을 충족하는 경기 0개")
        return None
    if checkpoint is not None:
        columns = ("game_start", "acs", "kills", "deaths", "kast", "headshot_pct", "agent")
        null_counts = {col: int(df[col].isna().sum()) if col in df else "COLUMN_MISSING" for col in columns}
        checkpoint(
            f"[DB ROWS] {player_label} puuid={puuid[:8]}... rows={len(df)}, "
            f"latest={df.iloc[0].get('game_start')}, null_counts={null_counts}"
        )
    try:
        try:
            df = add_match_side(df)
        except (KeyError, TypeError, ValueError) as exc:
            report(f"TEAM_INVALID: {exc}")
            return None
        try:
            df = add_win_column(df)
        except (KeyError, TypeError, ValueError) as exc:
            report(f"SCORE_INVALID: {exc}")
            return None
        feature = build_db_player_feature(df, report=report)
        if feature is not None and checkpoint is not None:
            checkpoint(f"[DB HIT] {player_label} puuid={puuid[:8]}... rows={len(df)}")
        return feature
    except (KeyError, TypeError, ValueError) as exc:
        report(f"FEATURE_INVALID: {type(exc).__name__}: {exc}")
        return None


def build_blue_team_from_db(conn, blue_team):
    return [_db_player_feature(conn, player["puuid"]) for player in blue_team]


def predict_blue_win(blue_team, red_team, save_json=False, db=None, debug_checkpoint=None, db_missing_players=None):
    start_time = time.perf_counter()
    checkpoint = debug_checkpoint or create_prediction_checkpoint()
    checkpoint(f"예측 파이프라인 시작: DB={'사용' if db is not None else '없음'}")
    if len(blue_team) != 5 or len(red_team) != 5:
        raise ValueError("양 팀은 반드시 5명이어야 합니다.")
    teams = [blue_team, red_team]
    players = [[None] * 5, [None] * 5]
    missing = {}
    counts = [dict(DB=0, CACHE=0, API_FALLBACK=0) for _ in teams]
    resolved = {}

    checkpoint("PUUID·DB·캐시 조회 시작")
    # Session을 사용하는 작업은 이 스레드에서만 순차 실행한다.
    for side, team in enumerate(teams):
        seen = set()
        for i, player in enumerate(team):
            puuid = player.get("puuid")
            if not puuid:
                name, tag = player.get("name"), player.get("tag")
                if not name or not tag:
                    raise ValueError(f"선수 {i + 1}: PUUID 또는 Riot ID가 필요합니다.")
                key = (name, tag)
                if key not in resolved:
                    resolved[key] = resolve_puuid(name, tag, db)
                puuid = resolved[key]
            if not puuid:
                raise ValueError(f"선수 {i + 1}: PUUID 조회 실패")
            if puuid in seen:
                raise ValueError("같은 팀에 중복 선수가 있습니다.")
            seen.add(puuid)
            player_label = f"{'BLUE' if side == 0 else 'RED'} 선수 {i + 1}"
            feature = _db_player_feature(db, puuid, checkpoint, player_label) if side == 0 else None
            if side == 0 and db is not None and feature is None and db_missing_players is not None:
                db_missing_players.append(puuid)
            source = "DB"
            if feature is None:
                feature = get_cached_player_feature(db, puuid)
                checkpoint(f"[CACHE {'HIT' if feature is not None else 'MISS'}] {player_label}")
                source = "CACHE"
            if feature is not None:
                players[side][i] = feature
                counts[side][source] += 1
            else:
                counts[side]["API_FALLBACK"] += 1
                missing.setdefault(puuid, []).append((side, i, player))

    checkpoint("PUUID·DB·캐시 조회 완료")
    # API가 끝나기 전에 예정된 데이터 소스를 표시한다.
    for label, count in zip(("BLUE", "RED"), counts):
        checkpoint(f"[{label} SOURCE SUMMARY] " + ", ".join(f"{k}={v}" for k, v in count.items()))

    # 양 팀의 미스만 함께 조회한다. 작업자에는 DB Session을 넘기지 않는다.
    def fetch(puuid):
        side, index, player = missing[puuid][0]
        label = f"{'BLUE' if side == 0 else 'RED'} 선수 {index + 1}"
        checkpoint(f"{label} API 피처 조회 시작")
        try:
            feature = build_player_feature(
                player.get("name") or f"PUUID={puuid[:8]}",
                player.get("tag") or "", puuid=puuid,
            )
        except Exception as exc:
            checkpoint(f"{label} API 피처 조회 실패: {type(exc).__name__}")
            raise
        checkpoint(f"{label} API 피처 조회 완료")
        return feature

    if missing:
        checkpoint(f"API 조회 시작: {len(missing)}명 (요청 제한 대기 포함)")
        with ThreadPoolExecutor(max_workers=min(6, len(missing))) as executor:
            fetched = list(executor.map(fetch, missing))
        checkpoint("API 조회 완료")
        checkpoint("API 피처 검증·배정·캐시 저장 시작")
        for puuid, feature in zip(missing, fetched):
            validate_player_feature(feature)
            if feature.get("puuid") != puuid:
                raise ValueError("API 피처 PUUID mismatch")
            for side, i, _ in missing[puuid]:
                players[side][i] = feature
            save_player_feature_cache(db, feature)
        checkpoint("API 피처 검증·배정 완료; " + ("캐시 저장 완료" if db is not None else "DB 없음: 캐시 저장 생략"))
    else:
        checkpoint("API 조회 생략: 전체 DB·캐시 적중")

    blue_players, red_players = players

    # =========================================================
    # 3. TEAM FEATURE
    # =========================================================

    checkpoint("팀 피처 생성 시작")
    X = build_team_feature(
        blue_players,
        red_players
    )
    checkpoint("팀 피처 생성 완료")
    # 디버그
    # print("\n[TEAM FEATURES]")
    # print(X.to_string(index=False))


    # =========================================================
    # 4. XGBoost 추론
    # =========================================================
    # 디버그
    # print("\n[MODEL INPUT]")
    # print(X.to_string(index=False))

    checkpoint("모델 추론 시작")
    proba = model.predict_proba(X)
    checkpoint("모델 추론 완료")

    checkpoint(f"[PREDICT PROBA] {proba}")
    # ----

    probability = float(
        proba[0][1]
    )

    # 디버그
    print(
        f"\n[FINAL PREDICTION] "
        f"Blue win probability = {probability:.4f}"
    )

    winner = "BLUE" if probability >= 0.5 else "RED"


    # =========================================================
    # 5. 결과 반환
    # =========================================================

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


    # =========================================================
    # 6. JSON 저장
    # =========================================================

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

    elapsed = time.perf_counter() - start_time

    print(
        f"[PREDICTION TOTAL TIME] "
        f"{elapsed:.2f}s"
    )

    print("========== PREDICTION END ==========\n")

    checkpoint("예측 파이프라인 완료")
    return result
