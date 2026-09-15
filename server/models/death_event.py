"""
death_events 테이블 ORM 모델. 사망 위치 원본 데이터.
한 번의 사망 기록 (라운드당 최대 5명 x 팀 x 라운드 수만큼 쌓임)
services/death_hotspot_service.py::get_death_hotspots가 이 테이블을 조회해
compute_player_hotspots로 넘길 points를 만든다.
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func

from database.connection import Base


class DeathEvent(Base):
    __tablename__ = "death_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(64), ForeignKey("matches.match_id"), nullable=False)
    team_id = Column(String(64), ForeignKey("teams.team_id"), nullable=False)
    player_id = Column(String(64), nullable=False)
    map_id = Column(String(50), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    round_num = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())