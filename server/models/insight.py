"""
insights 테이블 ORM 모델 (AI 리포트 - 팀/개인 서술형 결과, Layer2).
database/valo_brief.sql 9번 섹션 참고 - "우리팀 분석 > AI 리포트" 화면은 이미
스캐폴딩돼 있었지만 이 테이블에 실제로 쓰는 코드는 없었다(services/ai_report.py가
최초로 사용). AI_리포트_개발_설계.md 참고.

한 "리포트"는 여러 행으로 쪼개져 저장된다(문장 하나당 한 행) - upsert 키가 없으므로
재생성 시 해당 팀의 opponent_team_id IS NULL 행을 전부 지우고 새로 넣는 방식으로
"교체"한다(services/ai_report.py::_save_report 참고).
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database.connection import Base
from models.team import Team


class Insight(Base):
    __tablename__ = "insights"

    insight_id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    # 매치업(상대팀 비교) 리포트일 때만 채워짐 - 우리팀 자체 분석 리포트는 항상 NULL.
    opponent_team_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    # DB는 ENUM('team','player')이지만 team_stats_summary.stat_type과 같은 이유로
    # SQLAlchemy Enum 타입 없이 평문 String으로 매핑(이 프로젝트 공통 관례).
    target_type = Column(String(10), nullable=False, default="team")
    # target_type="player"일 때만 채워짐(riot_accounts.puuid).
    target_puuid = Column(String(64), ForeignKey("riot_accounts.puuid", ondelete="SET NULL"), nullable=True)
    # 'summary'(팀 개요) / 'strength' / 'weakness' / 'strategy'(전술 제안) / 'personal_feedback'
    # (미사용 - team/player 공통으로 strength/weakness를 쓰는 쪽을 택함, 4-1 참고) / 'agent_comment'.
    insight_type = Column(String(30), nullable=True)
    content = Column(Text, nullable=False)
    generated_at = Column(DateTime, nullable=False, server_default=func.now())

    team = relationship(Team, foreign_keys=[team_id])
    opponent_team = relationship(Team, foreign_keys=[opponent_team_id])
