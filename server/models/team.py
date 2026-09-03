"""
teams 테이블 ORM 모델 (회원가입/로그인/팀 프로필 겸용). database/valo_brief.sql 참고.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, func

from database.connection import Base


class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    login_id = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    privacy_agreed = Column(Boolean, nullable=False, default=False)
    team_name = Column(String(50), nullable=False)
    team_tag = Column(String(10), nullable=False)
    premier_team_id = Column(String(64), nullable=True)
    tier_id = Column(Integer, nullable=True)
    season = Column(String(20), nullable=True)
    conference = Column(String(50), nullable=True)
    division = Column(String(20), nullable=True)
    ranking_points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
