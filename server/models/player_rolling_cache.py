"""
player_rolling_cache 테이블 ORM 모델 (선수별 Rolling Feature 캐시).
database/valo_brief.sql, services/player_rolling_cache.py 공용.
"""
from sqlalchemy import Column, DateTime, Float, String, func

from database.connection import Base


class PlayerRollingCache(Base):
    __tablename__ = "player_rolling_cache"

    puuid = Column(String(64), primary_key=True)
    agent = Column(String(30), nullable=True)
    recent_acs = Column(Float, nullable=False)
    recent_kd = Column(Float, nullable=False)
    recent_kast = Column(Float, nullable=False)
    recent_headshot_pct = Column(Float, nullable=False)
    recent_winrate = Column(Float, nullable=False)
    computed_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
