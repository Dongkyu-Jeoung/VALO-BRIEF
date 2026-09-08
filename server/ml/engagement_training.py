"""
matches/match_player_stats DB(services/match_history.py가 opportunistic하게 축적)에서
교전 매치업 예측 모델(ml/train_engagement_model.py) 학습용 DataFrame을 만든다.
server/승부예측_성능_분석.md 7-2/7-3번 참고.

- teams에 둘 다 가입된(team_a_id/team_b_id가 NOT NULL인) 매치만 쓴다 - 미가입 팀은
  매치마다 신원을 이어붙일 방법이 없어(팀명/태그를 매치 행에 저장하지 않음) 시간순
  rolling feature를 계산할 수 없다.
- 각 매치의 피처(team_recent_*)는 반드시 "그 매치 이전"의 매치들만으로 계산한다(누수
  방지) - 그래서 팀마다 최초 몇 경기는 피처를 못 만들어 자동으로 학습 샘플에서 빠진다.
- 라벨(label_trade_rate/label_duelist_acs)은 ml/engagement_predictor.py와 완전히 같은
  계산 함수(trade_success_from_kills)로 만든다 - 학습 라벨과 라이브 추론 피처의 정의가
  어긋나지 않게 하기 위함(engagement_predictor.py 모듈 docstring 참고).
"""
import json as json_module
from collections import defaultdict

import pandas as pd
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ml.engagement_predictor import RECENT_MATCHES, trade_success_from_kills

FEATURE_COLUMNS = [
    "team_recent_trade_rate",
    "opponent_recent_trade_rate",
    "team_recent_duelist_acs",
    "opponent_recent_duelist_acs",
    "diff_trade_rate",
    "diff_duelist_acs",
]
LABEL_COLUMNS = ["label_trade_rate", "label_duelist_acs"]


def _load_registered_matches(db: Session) -> list[dict]:
    """team_a_id/team_b_id가 둘 다 채워진(=양쪽 다 가입된 팀) 매치를 시간순으로 로드."""
    rows = db.execute(text(
        "SELECT match_id, team_a_id, team_b_id, game_start, round_detail_json "
        "FROM matches "
        "WHERE team_a_id IS NOT NULL AND team_b_id IS NOT NULL "
        "ORDER BY game_start ASC"
    )).mappings().all()
    return [dict(r) for r in rows]


def _load_player_stats_by_match(db: Session, match_ids: list[str]) -> dict[str, list[dict]]:
    """match_id -> [match_player_stats 행들] 매핑."""
    if not match_ids:
        return {}
    stmt = text(
        "SELECT match_id, puuid, side, acs, role_type FROM match_player_stats WHERE match_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = db.execute(stmt, {"ids": match_ids}).mappings().all()
    by_match: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_match[r["match_id"]].append(dict(r))
    return by_match


def _extract_kills(round_detail_json) -> list[dict]:
    """matches.round_detail_json(JSON 컬럼 - 드라이버에 따라 dict로 이미 역직렬화됐거나
    문자열로 올 수 있어 방어적으로 둘 다 처리)에서 kills 배열만 꺼낸다."""
    if isinstance(round_detail_json, str):
        try:
            round_detail_json = json_module.loads(round_detail_json)
        except (TypeError, ValueError):
            return []
    if isinstance(round_detail_json, dict):
        return round_detail_json.get("kills") or []
    return []


def _match_trade_rate(round_detail_json, puuids: set[str]) -> float | None:
    """이 매치에서 puuids 로스터의 실제 트레이드 성공률(%) - ml/engagement_predictor.py::
    trade_success_from_kills를 그대로 재사용(라이브 예측 계산식과 동일하게 유지)."""
    if not puuids:
        return None
    traded, deaths = trade_success_from_kills(_extract_kills(round_detail_json), puuids)
    if deaths == 0:
        return None
    return round(traded / deaths * 100, 1)


def _match_duelist_acs(side_rows: list[dict]) -> float | None:
    """이 매치에서 role_type='Duelist'인 선수들의 평균 ACS(이미 match_player_stats.acs로
    저장돼 있어 다시 계산할 필요 없음 - services/match_history.py가 upsert 시점에 계산)."""
    acs_values = [r["acs"] for r in side_rows if r.get("role_type") == "Duelist" and r.get("acs") is not None]
    if not acs_values:
        return None
    return sum(acs_values) / len(acs_values)


def _recent_avg(values: list[float | None], n: int = RECENT_MATCHES) -> float | None:
    """최근 n건(None은 제외)의 평균 - 값이 하나도 없으면 None(아직 이력 없음)."""
    valid = [v for v in values[-n:] if v is not None]
    return sum(valid) / len(valid) if valid else None


def build_training_dataframe(db: Session) -> pd.DataFrame:
    """ml/train_engagement_model.py가 바로 학습에 쓸 수 있는 DataFrame(FEATURE_COLUMNS +
    LABEL_COLUMNS)을 만든다. 매치 하나당 최대 2개 샘플(team_a 관점 1개, team_b 관점 1개,
    서로 대칭)을 만든다 - 단, 그 팀의 이전 이력이 하나도 없거나(RECENT_MATCHES 미만도
    포함해서 평균 자체는 계산 가능하지만 이력 자체가 0건이면 제외) 이 매치의 라벨을
    계산할 수 없으면(로스터 데이터 누락 등) 그 방향의 샘플은 건너뛴다."""
    matches = _load_registered_matches(db)
    if not matches:
        return pd.DataFrame(columns=FEATURE_COLUMNS + LABEL_COLUMNS)

    match_ids = [m["match_id"] for m in matches]
    stats_by_match = _load_player_stats_by_match(db, match_ids)

    # team_id -> [(trade_rate, duelist_acs), ...] 시간순 관측 이력(현재 매치는 아직 안 들어감)
    history_by_team: dict[str, list[tuple]] = defaultdict(list)
    rows: list[dict] = []

    for m in matches:
        team_a, team_b = m["team_a_id"], m["team_b_id"]
        player_rows = stats_by_match.get(m["match_id"], [])
        red_rows = [r for r in player_rows if r["side"] == "red"]
        blue_rows = [r for r in player_rows if r["side"] == "blue"]
        red_puuids = {r["puuid"] for r in red_rows}
        blue_puuids = {r["puuid"] for r in blue_rows}

        label_a_trade = _match_trade_rate(m["round_detail_json"], red_puuids)
        label_b_trade = _match_trade_rate(m["round_detail_json"], blue_puuids)
        label_a_duelist = _match_duelist_acs(red_rows)
        label_b_duelist = _match_duelist_acs(blue_rows)

        team_a_hist = history_by_team[team_a]
        team_b_hist = history_by_team[team_b]
        a_trade_feat = _recent_avg([h[0] for h in team_a_hist])
        a_duelist_feat = _recent_avg([h[1] for h in team_a_hist])
        b_trade_feat = _recent_avg([h[0] for h in team_b_hist])
        b_duelist_feat = _recent_avg([h[1] for h in team_b_hist])

        def _make_row(team_feat_trade, opp_feat_trade, team_feat_duelist, opp_feat_duelist,
                      label_trade, label_duelist):
            if None in (team_feat_trade, opp_feat_trade, team_feat_duelist, opp_feat_duelist,
                        label_trade, label_duelist):
                return None
            return {
                "team_recent_trade_rate": team_feat_trade,
                "opponent_recent_trade_rate": opp_feat_trade,
                "team_recent_duelist_acs": team_feat_duelist,
                "opponent_recent_duelist_acs": opp_feat_duelist,
                "diff_trade_rate": team_feat_trade - opp_feat_trade,
                "diff_duelist_acs": team_feat_duelist - opp_feat_duelist,
                "label_trade_rate": label_trade,
                "label_duelist_acs": label_duelist,
            }

        row_a = _make_row(a_trade_feat, b_trade_feat, a_duelist_feat, b_duelist_feat,
                           label_a_trade, label_a_duelist)
        if row_a:
            rows.append(row_a)
        row_b = _make_row(b_trade_feat, a_trade_feat, b_duelist_feat, a_duelist_feat,
                           label_b_trade, label_b_duelist)
        if row_b:
            rows.append(row_b)

        # 이 매치의 실제 결과는 "다음" 매치부터 이력에 반영되도록 마지막에 추가한다
        # (누수 방지 - 위 피처 계산이 끝난 뒤에만 append).
        history_by_team[team_a].append((label_a_trade, label_a_duelist))
        history_by_team[team_b].append((label_b_trade, label_b_duelist))

    return pd.DataFrame(rows, columns=FEATURE_COLUMNS + LABEL_COLUMNS)
