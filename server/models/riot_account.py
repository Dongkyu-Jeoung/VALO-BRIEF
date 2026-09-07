"""
riot_accounts 테이블 ORM 모델 (로스터 개인 Riot 계정 캐시). database/valo_brief.sql 참고.
services/riot_accounts.py 공용.
"""
from sqlalchemy import Column, DateTime, Integer, String, func

from database.connection import Base


class RiotAccount(Base):
    __tablename__ = "riot_accounts"

    puuid = Column(String(64), primary_key=True)
    riot_name = Column(String(50), nullable=False)
    riot_tag = Column(String(10), nullable=False)
    region = Column(String(10), nullable=False)
    platform = Column(String(10), nullable=False, default="pc")
    account_level = Column(Integer, nullable=True)
    title = Column(String(100), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    current_rank = Column(String(30), nullable=True)
    current_rr = Column(Integer, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
