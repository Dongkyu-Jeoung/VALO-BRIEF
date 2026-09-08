"""
matches 테이블 ORM 모델 (매치 메타데이터 캐시). database/valo_brief.sql 4번 섹션 참고.
services/match_sync.py가 회원가입 시 프리미어 매치 이력을 미리 채워 넣을 때 쓴다.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from database.connection import Base
from models.team import Team


class Match(Base):
    __tablename__ = "matches"

    match_id = Column(String(64), primary_key=True)
    # ref_maps는 이 앱에 ORM 모델이 없는(원시 SQL로만 조회하는) 참조 테이블이라, 여기서
    # ForeignKey()로 걸면 flush 시 SQLAlchemy가 그 테이블을 찾지 못해 NoReferencedTableError가
    # 난다(실측 확인). DB 자체의 FK 제약은 valo_brief.sql에 이미 있으므로 컬럼만 선언한다
    # (models/prediction.py의 map_uuid와 동일한 이유로 동일하게 처리).
    map_uuid = Column(String(64), nullable=True)
    mode = Column(String(30), nullable=True)
    game_start = Column(DateTime, nullable=True)
    team_a_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    team_b_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    winner_team_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    rounds_won_a = Column(Integer, nullable=True)
    rounds_won_b = Column(Integer, nullable=True)
    round_detail_json = Column(JSON, nullable=True)
    api_source = Column(String(30), nullable=True)
    collected_at = Column(DateTime, nullable=False, server_default=func.now())

    # 세 FK가 모두 teams를 가리켜서 foreign_keys 명시가 필요함 (models/prediction.py와 동일 이유).
    team_a = relationship(Team, foreign_keys=[team_a_id])
    team_b = relationship(Team, foreign_keys=[team_b_id])
    winner_team = relationship(Team, foreign_keys=[winner_team_id])
