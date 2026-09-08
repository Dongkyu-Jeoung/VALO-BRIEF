"""
match_player_stats 테이블 ORM 모델 (매치별 선수 집계 스탯 캐시). database/valo_brief.sql
5번 섹션 참고. 현재는 services/match_sync.py만 쓴다 - 아직 이 테이블을 읽어 화면에
보여주는 라우터는 없음(추후 "우리팀 분석" 등 통계 탭이 Henrik 실시간 호출 대신 이
캐시를 읽도록 붙이면 됨).
"""
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.connection import Base
from models.match import Match
from models.riot_account import RiotAccount
from models.team import Team


class MatchPlayerStat(Base):
    __tablename__ = "match_player_stats"
    __table_args__ = (UniqueConstraint("match_id", "puuid", name="uq_match_player"),)

    stat_id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(64), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False)
    puuid = Column(String(64), ForeignKey("riot_accounts.puuid", ondelete="CASCADE"), nullable=False)
    team_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    is_mvp = Column(Boolean, nullable=False, default=False)
    # ref_agents/ref_weapons도 ORM 모델이 없는 참조 테이블이라 models/match.py의 map_uuid와
    # 같은 이유로 ForeignKey()를 걸지 않는다 (DB 자체 FK 제약은 valo_brief.sql에 이미 있음).
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

    match = relationship(Match)
    riot_account = relationship(RiotAccount)
    team = relationship(Team, foreign_keys=[team_id])
