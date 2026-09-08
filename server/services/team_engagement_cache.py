"""
team_engagement_cache 테이블 - 팀×매치당 한 행씩 쌓는 append-only 로그.

matches/match_player_stats에는 더 이상 원본을 저장하지 않기로 하면서(2026-09-08 재설계 -
server/승부예측_성능_분석.md 11번 참고), 이 표 하나가 "지금 이 팀의 최근 폼" 캐시와
"모델 재학습용 원본" 두 역할을 겸한다:

  services/match_history.py(팀 페이지 조회 시) / services/match_sync.py(회원가입 백필,
  내부적으로 match_history.upsert_match_history를 그대로 재사용)가 매치 상세(raw Henrik
  v2/match dict)를 받는 즉시, 그 매치 하나만의 트레이드 성공률/듀얼리스트 ACS를 계산해서
  (ml/engagement_predictor.py::trade_rate_from_matches/duelist_acs_from_matches를 매치
  1건짜리 리스트로 호출) 이 표에 (team_id, match_id) 한 행으로 upsert한다
  (upsert_match_engagement). round_detail_json이나 선수별 세부 스탯(KAST/첫킬/무기)은
  저장하지 않는다 - 이 교전 매치업 모델에 필요한 값만 남긴다.

  - "지금 폼" 조회(get_recent_team_engagement) = 그 팀의 최근 N행 평균 - DB 쿼리 한 번.
  - 학습 데이터(ml/engagement_training.py::build_training_dataframe) = 이 표의 행들을
    시간순으로 재생하며 그 시점까지의 rolling 평균을 피처로, 그 행 자체의 값을 라벨로
    쓴다 - matches/match_player_stats 없이 이 표 하나로 완전히 재구성한다.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from ml.engagement_predictor import RECENT_MATCHES
from models.team_engagement_cache import TeamEngagementCache

_KST = timezone(timedelta(hours=9))

# 킬 스위치 - False면 upsert_match_engagement가 아무것도 안 쓰고 get_recent_team_engagement도
# 조회를 건너뛴다(None 반환). 원본 자체가 이 표뿐이라(matches/match_player_stats를 더
# 이상 안 씀) 꺼두면 "우리 팀" 교전 예측이 통째로 비게 된다 - write-through 로직이
# 검증된 지금은 기본 True, 비상시(버그 대응 등)에만 끄는 용도로 남겨둔다.
ENGAGEMENT_CACHE_ENABLED = True


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def upsert_match_engagement(
    db: Session,
    team_id: str,
    match_id: str,
    *,
    opponent_team_id: str | None,
    game_start: datetime | None,
    trade_rate: float | None,
    duelist_acs: float | None,
) -> None:
    """write-through 진입점 - 매치 상세를 받은 그 자리에서 바로 호출한다(services/
    match_history.py). (team_id, match_id) 한 행을 upsert. ENGAGEMENT_CACHE_ENABLED가
    False면 조용히 스킵.

    "확인 후 삽입"(db.get으로 있는지 보고 없으면 add) 대신 MySQL 네이티브 INSERT ...
    ON DUPLICATE KEY UPDATE를 문장 하나로 실행한다 - 같은 팀의 같은 매치를 서로 다른
    세션(예: 팀 페이지를 거의 동시에 두 번 조회, 또는 회원가입 백필과 페이지 조회가
    겹침)이 동시에 upsert하면 "확인"과 "삽입" 사이에 경합이 생겨 PRIMARY KEY 중복
    IntegrityError가 났었다(2026-09-08 실측) - 이 방식은 MySQL이 행 잠금으로 원자적으로
    처리해줘서 그 경합 자체가 생기지 않는다."""
    if not ENGAGEMENT_CACHE_ENABLED:
        return

    stmt = mysql_insert(TeamEngagementCache).values(
        team_id=team_id,
        match_id=match_id,
        opponent_team_id=opponent_team_id,
        game_start=game_start,
        trade_rate=trade_rate,
        duelist_acs=duelist_acs,
        computed_at=_now_kst(),
    )
    stmt = stmt.on_duplicate_key_update(
        opponent_team_id=stmt.inserted.opponent_team_id,
        game_start=stmt.inserted.game_start,
        trade_rate=stmt.inserted.trade_rate,
        duelist_acs=stmt.inserted.duelist_acs,
        computed_at=stmt.inserted.computed_at,
    )
    db.execute(stmt)
    db.commit()


def has_match(db: Session, team_id: str, match_id: str) -> bool:
    """이미 이 팀 기준으로 캐싱된 매치인지(services/match_sync.py의 회원가입 백필이
    재실행돼도 같은 매치를 중복으로 다시 안 부르도록 하는 용도)."""
    return db.get(TeamEngagementCache, (team_id, match_id)) is not None


def get_recent_team_engagement(db: Session, team_id: str, n: int = RECENT_MATCHES) -> dict | None:
    """team_id의 최근 n개 행(매치) 평균 - routers/teams.py가 "우리 팀" 교전 피처로 그대로
    쓴다. 값이 하나도 없으면(가입 이후 매치가 하나도 안 쌓임, 또는 캐시가 꺼져 있음) None."""
    if not ENGAGEMENT_CACHE_ENABLED:
        return None

    rows = (
        db.query(TeamEngagementCache)
        .filter(TeamEngagementCache.team_id == team_id)
        .order_by(TeamEngagementCache.game_start.desc())
        .limit(n)
        .all()
    )
    if not rows:
        return None

    trade_values = [r.trade_rate for r in rows if r.trade_rate is not None]
    duelist_values = [r.duelist_acs for r in rows if r.duelist_acs is not None]
    if not trade_values and not duelist_values:
        return None

    return {
        "trade_rate": sum(trade_values) / len(trade_values) if trade_values else 50.0,
        "duelist_acs": sum(duelist_values) / len(duelist_values) if duelist_values else 0.0,
        "sample_matches": len(rows),
    }
