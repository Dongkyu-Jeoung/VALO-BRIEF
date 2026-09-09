"""
player_stats_summary 테이블 ORM 모델 (개인 단위 집계 통계 캐시). database/valo_brief.sql
7번 섹션 참고. services/my_team_player_detail.py가 "개인 분석 > 선수 상세" 데이터를
최초 계산 후 여기 캐싱해둔다(cache-aside, models/team_stats_summary.py와 동일 패턴) -
다음 조회부터는 라운드 단위 재계산 없이 그대로 읽는다.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database.connection import Base
from models.riot_account import RiotAccount


class PlayerStatsSummary(Base):
    __tablename__ = "player_stats_summary"
    __table_args__ = (UniqueConstraint("puuid", "stat_type", "dimension_key", name="uq_player_stats"),)

    summary_id = Column(Integer, primary_key=True, autoincrement=True)
    puuid = Column(String(64), ForeignKey("riot_accounts.puuid", ondelete="CASCADE"), nullable=False)
    # DB는 ENUM('weapon','hitbox','clutch','role_matchup','engagement','round_phase')이지만
    # team_stats_summary와 동일한 이유로 평문 String으로 매핑.
    stat_type = Column(String(20), nullable=False)
    dimension_key = Column(String(100), nullable=False)
    metrics_json = Column(JSON, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    riot_account = relationship(RiotAccount)
