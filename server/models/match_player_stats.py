"""
match_player_stats 테이블 ORM 모델 (매치별 선수 집계 스탯 캐시). database/valo_brief.sql 참고.
services/match_history.py 공용.
"""
from sqlalchemy import Boolean, Column, Float, Integer, JSON, String

from database.connection import Base

# models/match.py와 같은 이유로 다른 테이블 참조 컬럼도 ForeignKey() 없이 평범한 Column으로
# 선언한다 - 실제 FK 제약은 database/valo_brief.sql이 이미 강제함.


class MatchPlayerStats(Base):
    __tablename__ = "match_player_stats"

    stat_id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(64), nullable=False)
    puuid = Column(String(64), nullable=False)
    team_id = Column(String(64), nullable=True)
    is_mvp = Column(Boolean, nullable=False, default=False)
    agent_uuid = Column(String(64), nullable=True)
    role_type = Column(String(20), nullable=True)
    side = Column(String(10), nullable=True)
    acs = Column(Integer, nullable=True)
    kills = Column(Integer, nullable=True)
    deaths = Column(Integer, nullable=True)
    assists = Column(Integer, nullable=True)
    headshot_pct = Column(Float, nullable=True)
    kast = Column(Float, nullable=True)
    adr = Column(Integer, nullable=True)
    first_bloods = Column(Integer, nullable=True)
    first_deaths = Column(Integer, nullable=True)
    most_used_weapon_uuid = Column(String(64), nullable=True)
    detail_json = Column(JSON, nullable=True)
