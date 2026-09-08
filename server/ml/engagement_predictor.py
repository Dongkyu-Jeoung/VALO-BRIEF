"""
승부예측 페이지 "분석" 탭 ③번(교전 매치업 예측) 전용 모듈.
server/승부예측_성능_분석.md 6~7번 참고.

build_engagement_prediction()은 학습된 모델(models/engagement_model.pkl)이 있으면 그걸로
예측하고, 없으면(아직 학습 전 - 정상 상태) 결정론적 통계(6-3번 "0단계")로 값을 채워서
modelVersion="heuristic-v0"로 표시해 내려준다. 학습된 모델의 입력 피처는 이 결정론적
계산과 완전히 같은 함수(_trade_success_rate/_duelist_avg_acs)로 만든다 - ml/train_
engagement_model.py가 학습에 쓰는 피처와 여기 추론에 쓰는 피처가 어긋나면 안 되기 때문.

주의(중요): 트레이드 성공률 계산은 v2/match 스키마(services/henrik_api.py::get_match_detail
가 주는 형태 - killer_puuid/victim_puuid/kill_time_in_round가 최상위 평면 필드)를 전제로
한다. ml/valorant_git.py(별도의 v4/match 기반 승률 예측 파이프라인)의 킬 이벤트는 스키마가
달라서(killer.puuid처럼 중첩) 여기 함수들과 호환되지 않는다 - services/team_profile.py::
_first_blood_count와 동일한 필드명을 쓴다.

ml/predictor.py와 마찬가지로 이 모듈은 순수 함수 모음이다 - Henrik 호출도, DB 접근도
직접 하지 않는다. 호출부(routers/teams.py)가 이미 불러온 match_details(v2/match 응답
리스트)를 그대로 넘겨준다.
"""
from pathlib import Path

import joblib
import pandas as pd

from ml.team_feature import DUELISTS

# 팀원이 죽은 뒤 이 시간(ms) 안에 그 킬러가 처치되면 "트레이드 성공"으로 인정.
# ml/valorant_git.py::TRADE_WINDOW_MS와 같은 값(5초)을 쓴다 - 트레이드의 "정의" 자체는
# 두 파이프라인이 같아야 하지만, 위 주석대로 킬 이벤트 스키마(필드명)는 서로 다르다.
TRADE_WINDOW_MS = 5000

# 팀별 rolling feature에 최근 몇 경기를 쓸지 - ml/rolling.py::RECENT_MATCHES와 같은
# 값(5)으로 맞춰 일관성을 유지한다. ml/train_engagement_model.py도 이 상수를 그대로 쓴다.
RECENT_MATCHES = 5

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "engagement_model.pkl"

# model_loader.py처럼 모듈 임포트 시점에 joblib.load()를 바로 하면, 파일이 아직 없는
# 지금 상태에서 서버 전체가 임포트 에러로 못 뜬다 - 그래서 여기서는 첫 호출 때 지연 로드하고,
# 파일이 없으면 조용히 None으로 남겨서 "모델 학습 전" 상태를 정상 동작으로 처리한다.
_artifact = None
_artifact_loaded = False


def _get_artifact():
    """학습된 모델 아티팩트(dict: trade_model/duelist_model/feature_columns, ml/
    train_engagement_model.py가 저장하는 형식)가 있으면 로드해서 캐싱, 없으면
    None(정상 - 아직 학습 전)."""
    global _artifact, _artifact_loaded
    if not _artifact_loaded:
        _artifact = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
        _artifact_loaded = True
    return _artifact


def _team_roster(match: dict, team_name: str, team_tag: str) -> tuple[str | None, set[str]]:
    """매치에서 team_name/team_tag 로스터가 red/blue 중 어느 쪽인지와 puuid 집합을 찾는다.
    services/team_profile.py::_match_our_side와 동일한 판정 방식(이름/태그 대소문자 무시
    일치) - 이 모듈은 team_profile.py의 private 함수에 의존하지 않고 독립적으로 재구현한다."""
    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for side in ("red", "blue"):
        roster = (teams.get(side) or {}).get("roster") or {}
        if str(roster.get("name", "")).lower() == name_l and str(roster.get("tag", "")).lower() == tag_l:
            return side, set(roster.get("members") or [])
    return None, set()


def trade_success_from_kills(kills: list[dict], our_puuids: set[str]) -> tuple[int, int]:
    """kills(v2/match의 평면 킬 이벤트 리스트: round/kill_time_in_round/killer_puuid/
    victim_puuid) + our_puuids로부터 (트레이드 성공 횟수, 로스터 사망 횟수)를 계산한다.
    이 함수가 트레이드 계산의 유일한 소스 - _trade_success_rate(라이브 경로, raw match dict)와
    ml/engagement_training.py(학습 경로, DB의 matches.round_detail_json에서 복원한 kills)가
    둘 다 이 함수를 그대로 재사용해서 "라이브 예측 때 계산 방식"과 "학습 라벨 계산 방식"이
    절대 어긋나지 않게 한다."""
    traded = 0
    deaths = 0
    kills_by_round: dict[int, list] = {}
    for k in kills or []:
        kills_by_round.setdefault(k.get("round"), []).append(k)

    for round_kills in kills_by_round.values():
        sorted_kills = sorted(round_kills, key=lambda k: k.get("kill_time_in_round", 0))
        for kill in sorted_kills:
            victim_puuid = kill.get("victim_puuid")
            if victim_puuid not in our_puuids:
                continue
            deaths += 1
            killer_puuid = kill.get("killer_puuid")
            death_time = kill.get("kill_time_in_round", 0)
            for revenge in sorted_kills:
                if revenge.get("victim_puuid") != killer_puuid:
                    continue
                revenge_time = revenge.get("kill_time_in_round", 0)
                if 0 <= (revenge_time - death_time) <= TRADE_WINDOW_MS:
                    traded += 1
                break

    return traded, deaths


def trade_rate_from_matches(matches: list[dict], team_name: str, team_tag: str) -> float | None:
    """team_name/team_tag 로스터의 트레이드 성공률(%) - 여러 매치(raw v2/match dict 리스트,
    Henrik에서 갓 조회한 것)에 걸쳐 trade_success_from_kills를 누적한다. 데이터가 하나도
    없으면(로스터를 못 찾음/킬 이벤트 없음) None - 호출부가 "값을 못 냈다"와 "0%다"를
    구분할 수 있게 한다. routers/teams.py가 (아직 DB에 캐싱 안 된) 상대팀처럼 라이브
    match_details만 갖고 있을 때 직접 부른다 - build_engagement_prediction_from_features와
    짝을 이룸."""
    total_traded = 0
    total_deaths = 0
    for match in matches:
        if not match:
            continue
        _, our_puuids = _team_roster(match, team_name, team_tag)
        if not our_puuids:
            continue
        traded, deaths = trade_success_from_kills(match.get("kills") or [], our_puuids)
        total_traded += traded
        total_deaths += deaths

    if total_deaths == 0:
        return None
    return round(total_traded / total_deaths * 100, 1)


def duelist_acs_from_matches(matches: list[dict], team_name: str, team_tag: str) -> float | None:
    """team_name/team_tag 로스터 중 듀얼리스트 요원을 플레이한 선수들의 매치당 평균 ACS
    (score / rounds_played, services/team_profile.py의 acs_of()와 동일한 계산 방식을
    독립적으로 재구현). 듀얼리스트 매치업 "유불리"의 원재료 - 절대값보다 상대 팀과의
    비교(build_engagement_prediction)에서 의미가 생긴다."""
    acs_values: list[float] = []
    for match in matches:
        if not match:
            continue
        side, our_puuids = _team_roster(match, team_name, team_tag)
        if side is None:
            continue

        teams = match.get("teams") or {}
        opp_side = "blue" if side == "red" else "red"
        rounds_played = ((teams.get(side) or {}).get("rounds_won") or 0) + (
            (teams.get(opp_side) or {}).get("rounds_won") or 0
        )
        if not rounds_played:
            continue

        all_players = (match.get("players") or {}).get("all_players") or []
        for player in all_players:
            if player.get("puuid") not in our_puuids:
                continue
            if (player.get("character") or "") not in DUELISTS:
                continue
            score = (player.get("stats") or {}).get("score", 0)
            acs_values.append(score / rounds_played)

    if not acs_values:
        return None
    return sum(acs_values) / len(acs_values)


def _duelist_matchup_from_acs(our_acs: float, their_acs: float) -> dict:
    """두 팀의 듀얼리스트 평균 ACS를 0~100 스코어로 정규화해서 비교. 둘 다 0이면(듀얼리스트를
    플레이한 기록 자체가 없음) 50:50 무승부로 처리."""
    total = our_acs + their_acs
    our_score = round(our_acs / total * 100, 1) if total else 50.0
    their_score = round(100 - our_score, 1) if total else 50.0

    # ±5%p 이내는 "팽팽함"으로 본다 - 표본이 적을 때 근소한 차이로 유/불리를 단정하지
    # 않기 위한 안전마진(임의로 정한 임계값 - 데이터가 쌓이면 재검토 대상, 7번 참고).
    if our_score - their_score > 5:
        favor = "us"
    elif their_score - our_score > 5:
        favor = "them"
    else:
        favor = "even"

    return {"ourScore": our_score, "theirScore": their_score, "favor": favor}


def _predict_with_model(artifact: dict, our_trade, their_trade, our_duelist_acs, their_duelist_acs) -> dict:
    """학습된 XGBRegressor 2개(트레이드 성공률/듀얼리스트 ACS)로 예측. 입력 피처는
    ml/train_engagement_model.py가 학습에 쓴 것과 정확히 같은 컬럼 순서로 조립해야
    한다(artifact["feature_columns"]) - ml/team_feature.py::build_team_feature와 같은
    "피처 컬럼 순서를 저장해두고 그대로 맞춘다" 패턴."""
    row = {
        "team_recent_trade_rate": our_trade if our_trade is not None else 50.0,
        "opponent_recent_trade_rate": their_trade if their_trade is not None else 50.0,
        "team_recent_duelist_acs": our_duelist_acs or 0.0,
        "opponent_recent_duelist_acs": their_duelist_acs or 0.0,
    }
    row["diff_trade_rate"] = row["team_recent_trade_rate"] - row["opponent_recent_trade_rate"]
    row["diff_duelist_acs"] = row["team_recent_duelist_acs"] - row["opponent_recent_duelist_acs"]

    X = pd.DataFrame([row])[artifact["feature_columns"]]

    predicted_trade = float(artifact["trade_model"].predict(X)[0])
    predicted_duelist_acs = float(artifact["duelist_model"].predict(X)[0])

    predicted_trade = min(max(predicted_trade, 0.0), 100.0)
    predicted_duelist_acs = max(predicted_duelist_acs, 0.0)
    # 학습된 모델은 "team_a(우리팀) 관점 트레이드 성공률"만 예측한다 - 상대팀 관점은
    # 100에서 빼는 게 아니라(트레이드는 팀별로 독립적인 비율이라 합이 100일 필요 없음)
    # 상대팀을 team_a로 놓고 한 번 더 예측하는 게 정확하지만, 지금은 대칭 근사로
    # (100 - 우리팀 예측치)를 상대팀 값으로 쓴다 - 데이터가 쌓여 모델이 안정되면 상대팀도
    # 별도로 추론하도록 개선 가능(7-4번 참고).
    return {
        "trade": {
            "ourWinRate": round(predicted_trade, 1),
            "theirWinRate": round(100 - predicted_trade, 1),
        },
        "duelistMatchup": _duelist_matchup_from_acs(predicted_duelist_acs, their_duelist_acs or 0.0),
        "modelVersion": artifact.get("model_version", "engagement-v1"),
    }


def build_engagement_prediction_from_features(
    *,
    team_trade_rate: float | None,
    opponent_trade_rate: float | None,
    team_duelist_acs: float | None,
    opponent_duelist_acs: float | None,
) -> dict | None:
    """이미 계산된 트레이드 성공률/듀얼리스트 ACS 4개로 engagementPrediction shape을
    조립한다(server/승부예측_성능_분석.md 7-5번 API 계약, 9-4번 참고). 이 4개 값을 어디서
    구했는지는 이 함수가 신경 안 쓴다 - routers/teams.py가 우리팀은
    services/team_engagement_cache.py(DB 캐시, Henrik 호출 없음), 상대팀은 그 순간
    라이브로 받은 match_details(trade_rate_from_matches/duelist_acs_from_matches)처럼
    서로 다른 소스에서 얻어 여기로 넘긴다 - 두 소스 다 결국 같은 trade_success_from_kills
    계산식을 쓰므로 값 자체는 어긋나지 않는다."""
    if team_trade_rate is None and opponent_trade_rate is None and team_duelist_acs is None and opponent_duelist_acs is None:
        # 넷 다 없으면 굳이 50:50 가짜 값을 내려 "예측"인 척하지 않는다 - None을 반환해
        # 프론트(EngagementPredictionBlock)가 "모델 학습 전" 안내를 보여주게 한다.
        return None

    artifact = _get_artifact()
    if artifact is not None:
        return _predict_with_model(artifact, team_trade_rate, opponent_trade_rate, team_duelist_acs, opponent_duelist_acs)

    duelist_matchup = _duelist_matchup_from_acs(team_duelist_acs or 0.0, opponent_duelist_acs or 0.0)
    return {
        "trade": {
            "ourWinRate": team_trade_rate if team_trade_rate is not None else 50.0,
            "theirWinRate": opponent_trade_rate if opponent_trade_rate is not None else 50.0,
        },
        "duelistMatchup": duelist_matchup,
        "modelVersion": "heuristic-v0",
    }


def build_engagement_prediction(
    *,
    team_name: str,
    team_tag: str,
    team_matches: list[dict],
    opponent_name: str,
    opponent_tag: str,
    opponent_matches: list[dict],
) -> dict | None:
    """build_engagement_prediction_from_features의 얇은 래퍼 - 양쪽 다 라이브
    match_details(raw v2/match dict 리스트)를 갖고 있을 때 쓴다(예: 스크래치 테스트,
    두 팀 다 지금 막 조회한 경우). 실제 서비스 경로(routers/teams.py)는 우리팀은 DB
    캐시를 쓰므로 이 함수 대신 build_engagement_prediction_from_features를 직접 부른다."""
    return build_engagement_prediction_from_features(
        team_trade_rate=trade_rate_from_matches(team_matches, team_name, team_tag),
        opponent_trade_rate=trade_rate_from_matches(opponent_matches, opponent_name, opponent_tag),
        team_duelist_acs=duelist_acs_from_matches(team_matches, team_name, team_tag),
        opponent_duelist_acs=duelist_acs_from_matches(opponent_matches, opponent_name, opponent_tag),
    )
