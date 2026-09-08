"""
team_stats_summary 테이블 ORM 모델 (팀 단위 집계 통계 캐시). database/valo_brief.sql 6번
섹션 참고. services/my_team_analysis.py가 "우리팀 분석 > 팀 분석" 탭 데이터를 최초 계산
후 여기 캐싱해둔다(cache-aside) - 다음 조회부터는 라운드 단위 재계산 없이 그대로 읽는다.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database.connection import Base
from models.team import Team


class TeamStatsSummary(Base):
    __tablename__ = "team_stats_summary"
    __table_args__ = (UniqueConstraint("team_id", "stat_type", "dimension_key", name="uq_team_stats"),)

    summary_id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    # DB는 ENUM('map_side','agent','composition','round_phase','engagement')이지만
    # SQLAlchemy Enum 타입 없이 평문 String으로 매핑 - 다른 ENUM 컬럼(riot_accounts.platform
    # 등)도 이 프로젝트에서 별도 Enum 타입 없이 문자열로 다룬다.
    stat_type = Column(String(20), nullable=False)
    dimension_key = Column(String(100), nullable=False)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    metrics_json = Column(JSON, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    team = relationship(Team)
