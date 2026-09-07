"""
ref_player_cards / ref_player_titles 테이블 ORM 모델 (프로필 아바타/칭호 참조 캐시).
database/valo_brief.sql 참고. services/cosmetics.py 공용.
"""
from sqlalchemy import Column, DateTime, String, func

from database.connection import Base


class RefPlayerCard(Base):
    __tablename__ = "ref_player_cards"

    uuid = Column(String(64), primary_key=True)
    name_ko = Column(String(100), nullable=True)
    display_icon = Column(String(255), nullable=True)
    synced_at = Column(DateTime, server_default=func.now())


class RefPlayerTitle(Base):
    __tablename__ = "ref_player_titles"

    uuid = Column(String(64), primary_key=True)
    title_ko = Column(String(100), nullable=True)
    synced_at = Column(DateTime, server_default=func.now())
