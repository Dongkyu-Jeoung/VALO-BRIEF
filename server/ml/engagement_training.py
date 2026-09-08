"""
team_engagement_cache(services/match_history.py가 write-through로 채우는 팀×매치당
로그, services/team_engagement_cache.py 모듈 docstring 참고)에서 교전 매치업 예측 모델
(ml/train_engagement_model.py) 학습용 DataFrame을 만든다. server/승부예측_성능_분석.md
7-2/7-3/11번 참고.

2026-09-08 재설계: matches/match_player_stats에서 직접 집계하던 이전 버전과 달리, 이제
team_engagement_cache 표 하나만으로 재구성한다 - 그 표의 각 행이 곧 "그 팀이 그 매치에서
기록한 실제 값"(라벨 후보)이면서, 그 팀의 다음 매치들에 대해서는 "이전 이력"(피처 후보)
으로도 쓰인다.

- 상대도 가입 팀이라 같은 match_id로 2행(양쪽 관점)이 다 있는 매치만 학습 샘플로 쓴다 -
  한쪽만 가입돼 있으면 opponent_recent_* 피처를 만들 방법이 없다.
- 각 매치의 피처(team_recent_*)는 반드시 "그 매치 이전"의 행들만으로 계산한다(누수
  방지) - 그래서 팀마다 최초 몇 경기는 피처를 못 만들어 자동으로 학습 샘플에서 빠진다.
- 라벨(label_trade_rate/label_duelist_acs)은 ml/engagement_predictor.py와 완전히 같은
  계산 함수(trade_success_from_kills)로 만든다 - 학습 라벨과 라이브 추론 피처의 정의가
  어긋나지 않게 하기 위함(engagement_predictor.py 모듈 docstring 참고).

2026-09-08 재정리 - services/match_sync.py(회원가입 시 팀 이력 선동기화)와 컨벤션을
맞췄다(services/match_history.py 모듈 doc스트링 참고):
  - matches.team_a_id가 항상 "red 팀"이라는 보장이 없어졌다(이미 DB에 있는 매치는 어느
    쪽이 red/blue였는지 identity로 유지되기 때문). 그래서 로스터를 team_a_id/team_b_id와
    직접 비교해서 가른다 - side 컬럼(red/blue)이나 "team_a=red" 가정에 더 이상 의존하지 않는다.
  - match_player_stats.role_type이 이제 한글 라벨("타격대" 등)로 저장되므로 듀얼리스트
    판정도 한글 라벨(services.player_profile.ROLE_LABELS)로 비교한다.
- 라벨(label_trade_rate/label_duelist_acs)은 write-through 시점에 이미 ml/
  engagement_predictor.py와 같은 계산 함수로 만들어져 이 표에 저장돼 있으므로 여기서
  다시 계산하지 않고 그대로 읽는다 - 학습 라벨과 라이브 추론 피처의 정의가 어긋나지
  않는다는 보장은 그 write-through 경로(services/match_history.py)가 이미 갖고 있다.
"""
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from ml.engagement_predictor import RECENT_MATCHES, trade_success_from_kills
from services.player_profile import ROLE_LABELS
from models.team_engagement_cache import TeamEngagementCache

_DUELIST_LABEL = ROLE_LABELS["Duelist"]

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
    """team_a_id/team_b_id가 둘 다 채워진(=양쪽 다 가입된 팀) 매치를 시간순으로 로드.

    round_detail_json(매치당 용량이 큰 JSON)을 ORDER BY와 한 쿼리에 넣으면 MySQL이 그
    값까지 정렬 버퍼에 올려서 "Out of sort memory"가 난다(services/my_team_stats.py가
    먼저 겪고 고친 것과 동일한 문제, 실측 확인). 가벼운 컬럼으로 먼저 정렬하고
    round_detail_json은 정렬이 필요 없는 IN 조회로 따로 채운다."""
    rows = db.execute(text(
        "SELECT match_id, team_a_id, team_b_id, game_start "
        "FROM matches "
        "WHERE team_a_id IS NOT NULL AND team_b_id IS NOT NULL "
        "ORDER BY game_start ASC"
    )).mappings().all()
    matches = [dict(r) for r in rows]
    if not matches:
        return matches

    stmt = text(
        "SELECT match_id, round_detail_json FROM matches WHERE match_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    detail_by_id = {
        r["match_id"]: r["round_detail_json"]
        for r in db.execute(stmt, {"ids": [m["match_id"] for m in matches]}).mappings().all()
    }
    for m in matches:
        m["round_detail_json"] = detail_by_id.get(m["match_id"])
    return matches


def _load_player_stats_by_match(db: Session, match_ids: list[str]) -> dict[str, list[dict]]:
    """match_id -> [match_player_stats 행들] 매핑. side 대신 team_id로 로스터를 가른다
    (모듈 docstring 참고 - team_a_id/team_b_id에 고정 색상 의미가 없어졌기 때문)."""
    if not match_ids:
        return {}
    stmt = text(
        "SELECT match_id, puuid, team_id, acs, role_type FROM match_player_stats WHERE match_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = db.execute(stmt, {"ids": match_ids}).mappings().all()
    by_match: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_match[r["match_id"]].append(dict(r))
    return by_match


def _extract_kills(round_detail_json) -> list[dict]:
    """matches.round_detail_json(JSON 컬럼 - 드라이버에 따라 리스트로 이미 역직렬화됐거나
    문자열로 올 수 있어 방어적으로 둘 다 처리)에서 트레이드 판정에 필요한 평면 킬 이벤트
    목록을 복원한다. services/match_sync.py/match_history.py가 저장하는 형식(라운드 원본
    배열, 각 라운드의 player_stats[].kill_events)을 라운드 인덱스를 붙여 평탄화한다 -
    round_detail_json 자체에는 라운드 번호가 없고 배열 위치가 곧 라운드 번호다."""
    if isinstance(round_detail_json, str):
        try:
            round_detail_json = json_module.loads(round_detail_json)
        except (TypeError, ValueError):
            return []
    if not isinstance(round_detail_json, list):
        return []

    kills: list[dict] = []
    for round_idx, rnd in enumerate(round_detail_json):
        for player_stat in (rnd.get("player_stats") or []):
            for ke in (player_stat.get("kill_events") or []):
                kills.append({
                    "round": round_idx,
                    "kill_time_in_round": ke.get("kill_time_in_round"),
                    "killer_puuid": ke.get("killer_puuid"),
                    "victim_puuid": ke.get("victim_puuid"),
                })
    return kills


def _match_trade_rate(round_detail_json, puuids: set[str]) -> float | None:
    """이 매치에서 puuids 로스터의 실제 트레이드 성공률(%) - ml/engagement_predictor.py::
    trade_success_from_kills를 그대로 재사용(라이브 예측 계산식과 동일하게 유지)."""
    if not puuids:
        return None
    traded, deaths = trade_success_from_kills(_extract_kills(round_detail_json), puuids)
    if deaths == 0:
        return None
    return round(traded / deaths * 100, 1)


def _match_duelist_acs(team_rows: list[dict]) -> float | None:
    """이 매치에서 role_type=타격대(Duelist)인 선수들의 평균 ACS(이미 match_player_stats.acs로
    저장돼 있어 다시 계산할 필요 없음 - services/match_history.py가 upsert 시점에 계산).
    role_type은 이제 한글 라벨로 저장되므로 ROLE_LABELS["Duelist"]와 비교한다."""
    acs_values = [r["acs"] for r in team_rows if r.get("role_type") == _DUELIST_LABEL and r.get("acs") is not None]
    if not acs_values:
        return None
    return sum(acs_values) / len(acs_values)


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
        return pd.DataFrame(columns=FEATURE_COLUMNS + LABEL_COLUMNS)

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

    for m in matches:
        team_a, team_b = m["team_a_id"], m["team_b_id"]
        player_rows = stats_by_match.get(m["match_id"], [])
        # side(red/blue) 대신 team_id로 직접 가른다 - matches.team_a_id/team_b_id에 더
        # 이상 고정 색상 의미가 없어서(모듈 docstring 참고) team_id 비교가 유일하게 안전하다.
        a_rows = [r for r in player_rows if r["team_id"] == team_a]
        b_rows = [r for r in player_rows if r["team_id"] == team_b]
        a_puuids = {r["puuid"] for r in a_rows}
        b_puuids = {r["puuid"] for r in b_rows}

        label_a_trade = _match_trade_rate(m["round_detail_json"], a_puuids)
        label_b_trade = _match_trade_rate(m["round_detail_json"], b_puuids)
        label_a_duelist = _match_duelist_acs(a_rows)
        label_b_duelist = _match_duelist_acs(b_rows)

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
                           a.trade_rate, a.duelist_acs)
        if row_a:
            rows.append(row_a)
        row_b = _make_row(b_trade_feat, a_trade_feat, b_duelist_feat, a_duelist_feat,
                           b.trade_rate, b.duelist_acs)
        if row_b:
            rows.append(row_b)

        # 이 매치의 실제 결과는 "다음" 매치부터 이력에 반영되도록 마지막에 추가한다
        # (누수 방지 - 위 피처 계산이 끝난 뒤에만 append).
        history_by_team[a.team_id].append((a.trade_rate, a.duelist_acs))
        history_by_team[b.team_id].append((b.trade_rate, b.duelist_acs))

    return pd.DataFrame(rows, columns=FEATURE_COLUMNS + LABEL_COLUMNS)
