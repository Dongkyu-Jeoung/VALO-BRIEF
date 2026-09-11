"""
team_engagement_cache(services/match_history.py·services/match_sync.py가 write-through로
채우는 팀×매치당 로그, services/team_engagement_cache.py 모듈 docstring 참고)에서 교전
매치업 예측 모델(ml/train_engagement_model.py) 학습용 DataFrame을 만든다. server/승부예측_
성능_분석.md 7-2/7-3/11번 참고.

matches/match_player_stats는 다른 화면(우리팀 분석 페이지 등)을 위해 다시 원본을
저장하지만, 이 학습 파이프라인은 그 테이블을 직접 읽지 않는다 - team_engagement_cache
표 하나만으로 재구성한다. 그 표의 각 행이 곧 "그 팀이 그 매치에서 기록한 실제 값"
(라벨 후보)이면서, 그 팀의 다음 매치들에 대해서는 "이전 이력"(피처 후보)으로도 쓰인다.
routers/teams.py::get_team_analysis가 "우리 팀" 값을 읽을 때도 이 표(team_engagement_
cache.get_recent_team_engagement)를 그대로 쓰므로, 학습 피처와 라이브 추론 피처의 소스가
항상 일치한다.

- 상대도 가입 팀이라 같은 match_id로 2행(양쪽 관점)이 다 있는 매치만 학습 샘플로 쓴다 -
  한쪽만 가입돼 있으면 opponent_recent_* 피처를 만들 방법이 없다.
- 각 매치의 피처(team_recent_*)는 반드시 "그 매치 이전"의 행들만으로 계산한다(누수
  방지) - 그래서 팀마다 최초 몇 경기는 피처를 못 만들어 자동으로 학습 샘플에서 빠진다.
- 라벨(label_trade_rate/label_duelist_acs)은 write-through 시점에 이미 ml/
  engagement_predictor.py와 같은 계산 함수로 만들어져 이 표에 저장돼 있으므로 여기서
  다시 계산하지 않고 그대로 읽는다.
- label_win(META_COLUMNS)은 matches.winner_team_id와 team_id를 비교해 여기서 새로 만든다
  - team_engagement_cache에는 승패 정보가 없어서(팀당 트레이드율/ACS만 기록) matches
    테이블을 조인해야 한다. 매치가 아직 DB에 없거나 winner_team_id가 비어 있으면 None -
    ml/train_engagement_meta_model.py가 dropna로 그 행만 메타 학습에서 제외한다(기존
    base 모델 학습 표본에는 영향 없음).
"""
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from ml.engagement_predictor import RECENT_MATCHES
from models.match import Match
from models.team_engagement_cache import TeamEngagementCache

FEATURE_COLUMNS = [
    "team_recent_trade_rate",
    "opponent_recent_trade_rate",
    "team_recent_duelist_acs",
    "opponent_recent_duelist_acs",
    "diff_trade_rate",
    "diff_duelist_acs",
]
LABEL_COLUMNS = ["label_trade_rate", "label_duelist_acs"]

# 스태킹 메타 모델(ml/train_engagement_meta_model.py) 전용 부가 컬럼 - 실제 매치 승패
# (label_win)와 그 출처(team_id/match_id)를 같은 프레임에 실어보낸다. FEATURE_COLUMNS/
# LABEL_COLUMNS만 쓰는 기존 base 모델 학습(ml/train_engagement_model.py)에는 영향 없다
# (해당 스크립트는 필요한 컬럼만 선택해서 씀).
META_COLUMNS = ["team_id", "match_id", "label_win"]

_MIN_DATETIME = datetime.min


def _recent_avg(values: list[float | None], n: int = RECENT_MATCHES) -> float | None:
    """최근 n건(None은 제외)의 평균 - 값이 하나도 없으면 None(아직 이력 없음)."""
    valid = [v for v in values[-n:] if v is not None]
    return sum(valid) / len(valid) if valid else None


def build_training_dataframe(db: Session) -> pd.DataFrame:
    """ml/train_engagement_model.py가 바로 학습에 쓸 수 있는 DataFrame(FEATURE_COLUMNS +
    LABEL_COLUMNS)을 만든다. 매치 하나당 최대 2개 샘플(각 팀 관점 1개씩, 서로 대칭)을
    만든다 - 단, 상대가 미가입 팀이거나(같은 match_id에 행이 하나뿐) 그 팀의 이전 이력이
    하나도 없으면 그 방향의 샘플은 건너뛴다."""
    all_rows = db.query(TeamEngagementCache).order_by(TeamEngagementCache.game_start.asc()).all()
    if not all_rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS + LABEL_COLUMNS + META_COLUMNS)

    # 매치별 승자 - 스태킹 메타 모델의 정답 라벨(label_win)을 만드는 데만 쓴다. 모르는
    # 매치(아직 안 끝났거나 매치 자체가 DB에 없음)는 None으로 남겨 메타 학습에서만 제외되고
    # (dropna), 기존 base 모델(trade_model/duelist_model) 학습 표본에서는 계속 쓰인다.
    winner_by_match: dict[str, str | None] = dict(
        db.query(Match.match_id, Match.winner_team_id).all()
    )

    by_match: dict[str, list[TeamEngagementCache]] = defaultdict(list)
    for r in all_rows:
        by_match[r.match_id].append(r)

    match_order = sorted(
        by_match.keys(),
        key=lambda mid: min((r.game_start or _MIN_DATETIME) for r in by_match[mid]),
    )

    # team_id -> [(trade_rate, duelist_acs), ...] 시간순 관측 이력(현재 매치는 아직 안 들어감)
    history_by_team: dict[str, list[tuple]] = defaultdict(list)
    rows: list[dict] = []

    for match_id in match_order:
        entries = by_match[match_id]

        # 양쪽 다 가입 팀이어야(서로가 서로를 opponent_team_id로 가리키는 행 2개) 학습
        # 샘플을 만들 수 있다 - 아니면 각자 자기 이력에만 반영하고 건너뛴다.
        paired = (
            len(entries) == 2
            and entries[0].opponent_team_id == entries[1].team_id
            and entries[1].opponent_team_id == entries[0].team_id
        )
        if not paired:
            for r in entries:
                history_by_team[r.team_id].append((r.trade_rate, r.duelist_acs))
            continue

        a, b = entries
        a_hist, b_hist = history_by_team[a.team_id], history_by_team[b.team_id]
        a_trade_feat = _recent_avg([h[0] for h in a_hist])
        a_duelist_feat = _recent_avg([h[1] for h in a_hist])
        b_trade_feat = _recent_avg([h[0] for h in b_hist])
        b_duelist_feat = _recent_avg([h[1] for h in b_hist])

        winner_team_id = winner_by_match.get(match_id)

        def _make_row(team_id, team_feat_trade, opp_feat_trade, team_feat_duelist, opp_feat_duelist,
                      label_trade, label_duelist):
            if None in (team_feat_trade, opp_feat_trade, team_feat_duelist, opp_feat_duelist,
                        label_trade, label_duelist):
                return None
            label_win = None if winner_team_id is None else int(team_id == winner_team_id)
            return {
                "team_recent_trade_rate": team_feat_trade,
                "opponent_recent_trade_rate": opp_feat_trade,
                "team_recent_duelist_acs": team_feat_duelist,
                "opponent_recent_duelist_acs": opp_feat_duelist,
                "diff_trade_rate": team_feat_trade - opp_feat_trade,
                "diff_duelist_acs": team_feat_duelist - opp_feat_duelist,
                "label_trade_rate": label_trade,
                "label_duelist_acs": label_duelist,
                "team_id": team_id,
                "match_id": match_id,
                "label_win": label_win,
            }

        row_a = _make_row(a.team_id, a_trade_feat, b_trade_feat, a_duelist_feat, b_duelist_feat,
                           a.trade_rate, a.duelist_acs)
        if row_a:
            rows.append(row_a)
        row_b = _make_row(b.team_id, b_trade_feat, a_trade_feat, b_duelist_feat, a_duelist_feat,
                           b.trade_rate, b.duelist_acs)
        if row_b:
            rows.append(row_b)

        # 이 매치의 실제 결과는 "다음" 매치부터 이력에 반영되도록 마지막에 추가한다
        # (누수 방지 - 위 피처 계산이 끝난 뒤에만 append).
        history_by_team[a.team_id].append((a.trade_rate, a.duelist_acs))
        history_by_team[b.team_id].append((b.trade_rate, b.duelist_acs))

    return pd.DataFrame(rows, columns=FEATURE_COLUMNS + LABEL_COLUMNS + META_COLUMNS)
