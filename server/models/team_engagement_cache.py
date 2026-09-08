"""
team_engagement_cache 테이블 ORM 모델.

팀당 한 행이 아니라 "팀 x 매치"당 한 행씩 쌓이는 append-only 로그다(2026-09-08 재설계 -
matches/match_player_stats에는 더 이상 원본을 저장하지 않기로 하면서, 이 표 하나가
"지금 이 팀의 최근 폼" 캐시와 "모델 재학습용 원본" 두 역할을 겸한다 - services/
team_engagement_cache.py 모듈 docstring, server/승부예측_성능_분석.md 11번 참고).

한 매치에 가입 팀이 두 팀 다 참가했으면 팀마다 한 행씩(같은 match_id로 총 2행) 쌓인다.
trade_rate/duelist_acs는 그 팀이 "이 매치 한 건"에서 기록한 실제 값 - 계산 불가하면
(듀얼리스트 픽 없음, 킬 이벤트 없음 등) NULL.
"""
from sqlalchemy import Column, DateTime, Float, String

from database.connection import Base


class TeamEngagementCache(Base):
    __tablename__ = "team_engagement_cache"

    team_id = Column(String(64), primary_key=True)
    match_id = Column(String(64), primary_key=True)
    # 상대도 가입 팀이면 그 team_id, 아니면 NULL - ml/engagement_training.py가 "양쪽 다
    # 가입 팀인 매치"인지 판단해 학습 샘플(피처+라벨 쌍)을 만들 때 이 값으로 짝을 찾는다.
    # Team에 FK는 걸지 않음(matches.team_a_id/team_b_id도 FK 없던 기존 관례와 동일).
    opponent_team_id = Column(String(64), nullable=True)
    game_start = Column(DateTime, nullable=True)
    trade_rate = Column(Float, nullable=True)
    duelist_acs = Column(Float, nullable=True)
    computed_at = Column(DateTime, nullable=False)
