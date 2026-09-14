"""
승부예측 페이지 "분석" 탭 ③번(교전 매치업 예측) 전용 모듈.
server/승부예측_성능_분석.md 6~7번 참고.

build_engagement_prediction()은 학습된 모델(models/engagement_meta_model.pkl - base
모델 2개와 메타 모델이 전부 한 파일에 들어있다, ml/train_engagement_meta_model.py 참고)이
있으면 그걸로 예측하고, 없으면(아직 학습 전 - 정상 상태) 결정론적 통계(6-3번 "0단계")로
값을 채워서 modelVersion="heuristic-v0"로 표시해 내려준다. 학습된 모델의 입력 피처는
이 결정론적 계산과 완전히 같은 함수(_trade_success_rate/_duelist_avg_acs)로 만든다 -
학습에 쓰는 피처와 여기 추론에 쓰는 피처가 어긋나면 안 되기 때문.

2026-09-11: 원래 base 모델(engagement_model.pkl)과 메타 모델(engagement_meta_model.pkl)을
파일 2개로 따로 학습·저장했으나, 따로 재학습하다 버전이 어긋나는 사고가 있어 하나로
합쳤다 - 이제 artifact 하나 안에 trade_model/duelist_model/meta_model이 전부 들어있다.
artifact["meta_model"]이 None이면(메타 학습에 쓸 승패 라벨 표본이 아직 부족한 경우)
"최종 교전 승률"(finalPrediction) 키 자체를 응답에서 뺀다(하위 호환 - 기존 프론트
계약을 깨지 않음). 어느 base 입력에 얼마나 가중치를 줄지는 하드코딩이 아니라 메타
모델이 실제 매치 승패로 학습해서 정한다(교전매치업_예측_분석.md 8번 참고).

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
import logging
import warnings

import joblib
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning

from ml.team_feature import DUELISTS

# 팀원이 죽은 뒤 이 시간(ms) 안에 그 킬러가 처치되면 "트레이드 성공"으로 인정.
# ml/valorant_git.py::TRADE_WINDOW_MS와 같은 값(5초)을 쓴다 - 트레이드의 "정의" 자체는
# 두 파이프라인이 같아야 하지만, 위 주석대로 킬 이벤트 스키마(필드명)는 서로 다르다.
TRADE_WINDOW_MS = 5000

# 팀별 rolling feature에 최근 몇 경기를 쓸지 - ml/rolling.py::RECENT_MATCHES와 같은
# 값(5)으로 맞춰 일관성을 유지한다. ml/train_engagement_model.py도 이 상수를 그대로 쓴다.
RECENT_MATCHES = 5

# base 모델(trade_model/duelist_model) + 메타 모델(meta_model, 없을 수 있음)이 전부
# 한 파일에 들어있다 - ml/train_engagement_meta_model.py가 유일한 저장 지점.
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "engagement_meta_model.pkl"

# model_loader.py처럼 모듈 임포트 시점에 joblib.load()를 바로 하면, 파일이 아직 없는
# 지금 상태에서 서버 전체가 임포트 에러로 못 뜬다 - 그래서 여기서는 첫 호출 때 지연 로드하고,
# 파일이 없으면 조용히 None으로 남겨서 "모델 학습 전" 상태를 정상 동작으로 처리한다.
_artifact = None
_artifact_loaded = False
logger = logging.getLogger(__name__)


def _get_artifact():
    """학습된 모델 아티팩트(dict: trade_model/duelist_model/feature_columns/meta_model
    (None일 수 있음)/meta_feature_columns, ml/train_engagement_meta_model.py가 저장하는
    형식)가 있으면 로드해서 캐싱, 없으면 None(정상 - 아직 학습 전)."""
    global _artifact, _artifact_loaded
    if not _artifact_loaded:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", InconsistentVersionWarning)
                _artifact = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
        except InconsistentVersionWarning as exc:
            logger.error("[ENGAGEMENT MODEL INCOMPATIBLE] path=%s estimator=%s saved=%s runtime=%s; using heuristic-v0 until dependencies are aligned and server restarted", MODEL_PATH, exc.estimator_name, exc.original_sklearn_version, exc.current_sklearn_version)
            _artifact = None
        _artifact_loaded = True
    return _artifact


def _team_roster(match: dict, team_name: str, team_tag: str) -> tuple[str | None, set[str]]:
    """매치에서 team_name/team_tag 로스터가 red/blue 중 어느 쪽인지와 puuid 집합을 찾는다.
    services/team_profile.py::_match_our_side와 동일한 판정 방식(이름/태그 대소문자 무시
    일치) - 이 모듈은 team_profile.py의 private 함수에 의존하지 않고 독립적으로 재구현한다.

    2026-09-14 버그 수정: roster.get("name")도 team_name과 똑같이 strip()해야 한다 -
    Henrik이 내려주는 roster.name에 공백이 붙어 있는 팀이 실제로 있었다(예: "XLA  ").
    입력값만 strip하고 roster 쪽은 안 하면 둘 다 사실상 같은 팀인데 비교가 실패해서
    trade_rate/duelist_acs가 계산 가능한 매치인데도 계속 None으로 나왔다(team_engagement_
    cache 백필 중 실제 사례로 발견 - scripts/backfill_engagement_cache.py)."""
    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for side in ("red", "blue"):
        roster = (teams.get(side) or {}).get("roster") or {}
        if str(roster.get("name", "")).strip().lower() == name_l and str(roster.get("tag", "")).strip().lower() == tag_l:
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


def win_rate_from_matches(matches: list[dict], team_name: str, team_tag: str) -> float | None:
    """team_name/team_tag 로스터의 최근 매치 승률(%) - teams.{side}.has_won을 그대로
    집계한다. diff_win_rate(이 값의 우리팀-상대팀 차이)가 실제 승패와의
    상관계수 0.493으로 diff_trade_rate(0.276)보다도 강한 신호였다 - services/
    team_engagement_cache.py가 write-through 시점에 저장하는 win 컬럼과 정확히 같은
    계산(ml/engagement_training.py 참고), 여기서는 DB 캐시가 없는 쪽(주로 상대팀,
    아직 검색 이력이 없는 미가입 팀 등)을 위해 라이브 match_details로 직접 집계한다."""
    wins = 0
    total = 0
    for match in matches:
        if not match:
            continue
        side, our_puuids = _team_roster(match, team_name, team_tag)
        if side is None:
            continue
        total += 1
        if (match.get("teams") or {}).get(side, {}).get("has_won"):
            wins += 1

    if total == 0:
        return None
    return round(wins / total * 100, 1)


def normalize_to_100(our_value: float, their_value: float) -> tuple[float, float]:
    """두 팀의 원본 관측치(각자 독립적으로 계산된 값 - team_engagement_cache.trade_rate처럼
    서로 다른 표본에서 나와 합이 100일 필요가 없는 값)를 "우리 vs 상대" 대결 구도의 0~100
    스코어 쌍으로 정규화한다 - 프론트 DuelCompareBar가 항상 합이 100인 두 값을 그린다고
    전제하므로, 여기서 미리 맞춰서 내려보낸다(그렇지 않으면 바 너비와 표시 숫자가 어긋나
    보임). 둘 다 0이면(표본이 아예 없음) 50:50 무승부로 처리."""
    total = our_value + their_value
    our_pct = round(our_value / total * 100, 1) if total else 50.0
    their_pct = round(100 - our_pct, 1) if total else 50.0
    return our_pct, their_pct


def _duelist_matchup_from_acs(our_acs: float, their_acs: float) -> dict:
    """두 팀의 듀얼리스트 평균 ACS를 0~100 스코어로 정규화해서 비교."""
    our_score, their_score = normalize_to_100(our_acs, their_acs)

    # ±5%p 이내는 "팽팽함"으로 본다 - 표본이 적을 때 근소한 차이로 유/불리를 단정하지
    # 않기 위한 안전마진(임의로 정한 임계값 - 데이터가 쌓이면 재검토 대상, 7번 참고).
    if our_score - their_score > 5:
        favor = "us"
    elif their_score - our_score > 5:
        favor = "them"
    else:
        favor = "even"

    return {"ourScore": our_score, "theirScore": their_score, "favor": favor}


def _predict_with_model(
    artifact: dict, our_trade, their_trade, our_duelist_acs, their_duelist_acs,
    our_win_rate=None, their_win_rate=None,
) -> dict:
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

    # 상대팀 관점 피처(우리/상대를 서로 바꿔치기) - 2026-09-13: 화면에 보여주는 상대팀
    # 값이 "우리팀 예측치를 100에서 뺀 것"일 뿐 상대팀의 실제 기록과 무관해서(예: 상대
    # 실제 트레이드 22.5%인데 화면엔 74.9%로 표시되는 등) 실제 근거와 화면이 어긋난다는
    # 지적이 있었다(2026-09-13 실사용 사례 - Spicy Nuguri vs SYSTEM SEOUL). 상대팀도
    # 같은 모델로 독립적으로 한 번 더 예측해서 화면에 실제 근거가 있는 값을 보여준다.
    their_row = {
        "team_recent_trade_rate": row["opponent_recent_trade_rate"],
        "opponent_recent_trade_rate": row["team_recent_trade_rate"],
        "team_recent_duelist_acs": row["opponent_recent_duelist_acs"],
        "opponent_recent_duelist_acs": row["team_recent_duelist_acs"],
        "diff_trade_rate": -row["diff_trade_rate"],
        "diff_duelist_acs": -row["diff_duelist_acs"],
    }

    X_ours = pd.DataFrame([row])[artifact["feature_columns"]]
    X_theirs = pd.DataFrame([their_row])[artifact["feature_columns"]]

    predicted_trade_ours = min(max(float(artifact["trade_model"].predict(X_ours)[0]), 0.0), 100.0)
    predicted_trade_theirs = min(max(float(artifact["trade_model"].predict(X_theirs)[0]), 0.0), 100.0)
    predicted_duelist_ours = max(float(artifact["duelist_model"].predict(X_ours)[0]), 0.0)
    predicted_duelist_theirs = max(float(artifact["duelist_model"].predict(X_theirs)[0]), 0.0)

    # 화면 표시용 - 독립적으로 나온 두 예측치를 normalize_to_100으로 합이 100%가 되게
    # 맞춘다(heuristic-v0/듀얼리스트 비교와 동일한 방식) - 더 이상 "100에서 빼기"가 아니라
    # 상대팀도 실제로 예측된 값을 근거로 화면에 나간다.
    trade_our_pct, trade_their_pct = normalize_to_100(predicted_trade_ours, predicted_trade_theirs)
    duelist_matchup = _duelist_matchup_from_acs(predicted_duelist_ours, predicted_duelist_theirs)

    result = {
        "trade": {
            "ourWinRate": trade_our_pct,
            "theirWinRate": trade_their_pct,
        },
        "duelistMatchup": duelist_matchup,
        "modelVersion": artifact.get("model_version", "engagement-v2"),
    }

    # 스태킹 메타 모델 - 위 두 base 모델의 예측치(P_trade=트레이드 성공률, P_match=듀얼리스트
    # 매치업 정규화 점수)를 입력으로 받아 "최종 교전 승률" 하나로 합친다. 두 입력에 실제로
    # 얼마나 가중치를 주는지는 하드코딩이 아니라 ml/train_engagement_meta_model.py가 실제
    # 매치 승패(label_win)로 학습해서 정한다 - 8번(VALO-BRIEF 루트의 교전매치업_예측_분석.md) 참고.
    # 표본 부족으로 메타 단계가 아직 안 됐으면 artifact["meta_model"]이 None이다.
    meta_model = artifact.get("meta_model")
    if meta_model is not None:
        # 주의: 메타 모델은 학습 때 정확히 이 정의로 만들어진 p_trade/p_match를 봤다
        # (ml/train_engagement_meta_model.py::_out_of_fold_meta_features) - p_trade는
        # "우리팀 예측치 원본"(방금 위에서 화면용으로 정규화한 값이 아님), p_match는
        # "우리팀 예측 듀얼리스트 vs 상대팀 실측(원본 입력값) 듀얼리스트"다. 화면 표시가
        # 상대팀도 예측치로 바뀌었다고 해서 메타 입력까지 같이 바꾸면 학습 때 본 분포와
        # 어긋나(train/inference 피처 불일치) 메타 모델이 엉뚱하게 작동한다 - 그래서 이
        # 둘은 화면용 값과 별개로 예전 정의 그대로 계산한다.
        p_trade = predicted_trade_ours
        p_match = normalize_to_100(predicted_duelist_ours, their_duelist_acs or 0.0)[0]
        # diff_trade_rate/diff_duelist_acs를 p_trade/p_match와 같이 메타 피처에 넣는다 -
        # p_trade는 우리팀의 절대적인 예측 트레이드 성공률일 뿐 상대와의 비교가 아닌데
        # 승패는 상대적 우위로 갈려서(2026-09-12 실측 - diff_trade_rate가 실제 승패와의
        # 상관계수 0.276로 base 모델의 어떤 예측치보다 큼), 학습 때 이미 이 두 값을 추가로
        # 넣게 바꿨다(ml/train_engagement_meta_model.py 참고) - 추론도 반드시 같은 피처
        # 구성을 써야 한다.
        # diff_win_rate(최근 승률 차이)도 같이 넣는다 - 2026-09-12(2차) 실측 상관계수
        # 0.493으로 diff_trade_rate(0.276)보다도 강한 신호였다. our_win_rate/their_win_rate가
        # 없으면(집계 실패 등) 50.0(무승부 가정)으로 대체 - team_recent_trade_rate 등과
        # 동일한 fallback 관례.
        diff_win_rate = (our_win_rate if our_win_rate is not None else 50.0) - (
            their_win_rate if their_win_rate is not None else 50.0
        )
        meta_X = pd.DataFrame([{
            "p_trade": p_trade,
            "p_match": p_match,
            "diff_trade_rate": row["diff_trade_rate"],
            "diff_duelist_acs": row["diff_duelist_acs"],
            "diff_win_rate": diff_win_rate,
        }])[artifact["meta_feature_columns"]]
        our_final = float(meta_model.predict_proba(meta_X)[0][1]) * 100
        result["finalPrediction"] = {
            "ourWinRate": round(our_final, 1),
            "theirWinRate": round(100 - our_final, 1),
            "modelVersion": artifact.get("model_version", "engagement-meta-v2"),
        }

    return result


def build_engagement_prediction_from_features(
    *,
    team_trade_rate: float | None,
    opponent_trade_rate: float | None,
    team_duelist_acs: float | None,
    opponent_duelist_acs: float | None,
    team_win_rate: float | None = None,
    opponent_win_rate: float | None = None,
) -> dict | None:
    """이미 계산된 트레이드 성공률/듀얼리스트 ACS(+승률) 6개로 engagementPrediction
    shape을 조립한다(server/승부예측_성능_분석.md 7-5번 API 계약, 9-4번 참고). 이 값들을
    어디서 구했는지는 이 함수가 신경 안 쓴다 - routers/teams.py가 우리팀은
    services/team_engagement_cache.py(DB 캐시, Henrik 호출 없음), 상대팀은 그 순간
    라이브로 받은 match_details(trade_rate_from_matches/duelist_acs_from_matches/
    win_rate_from_matches)처럼 서로 다른 소스에서 얻어 여기로 넘긴다.
    team_win_rate/opponent_win_rate는 메타 모델(최종 교전 승률)에만 쓰인다 - trade/
    duelistMatchup 자체의 계산에는 관여하지 않는다."""
    if team_trade_rate is None and opponent_trade_rate is None and team_duelist_acs is None and opponent_duelist_acs is None:
        # 넷 다 없으면 굳이 50:50 가짜 값을 내려 "예측"인 척하지 않는다 - None을 반환해
        # 프론트(EngagementPredictionBlock)가 "모델 학습 전" 안내를 보여주게 한다.
        return None

    artifact = _get_artifact()
    if artifact is not None:
        return _predict_with_model(
            artifact, team_trade_rate, opponent_trade_rate, team_duelist_acs, opponent_duelist_acs,
            team_win_rate, opponent_win_rate,
        )

    duelist_matchup = _duelist_matchup_from_acs(team_duelist_acs or 0.0, opponent_duelist_acs or 0.0)
    our_trade_pct, their_trade_pct = normalize_to_100(team_trade_rate or 0.0, opponent_trade_rate or 0.0)
    return {
        "trade": {
            "ourWinRate": our_trade_pct,
            "theirWinRate": their_trade_pct,
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
        team_win_rate=win_rate_from_matches(team_matches, team_name, team_tag),
        opponent_win_rate=win_rate_from_matches(opponent_matches, opponent_name, opponent_tag),
    )
