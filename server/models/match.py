"""
matches 테이블 ORM 모델 (매치 메타데이터 캐시). database/valo_brief.sql 참고.
services/match_history.py 공용 - 승부예측 분석 탭 ③번(교전 매치업 예측) 학습 데이터
축적용(server/승부예측_성능_분석.md 7-2번).
"""
from sqlalchemy import Column, DateTime, Integer, JSON, String, func

from database.connection import Base

# 다른 모델 파일(models/team.py, models/riot_account.py)과 같은 관례로, 다른 테이블을
# 참조하는 컬럼도 SQLAlchemy ForeignKey()로 감싸지 않고 평범한 Column으로만 선언한다 -
# 실제 FK 제약은 DB 스키마(database/valo_brief.sql)가 이미 강제하고, ref_maps/ref_agents/
# ref_weapons는 이 프로젝트에 ORM 모델 자체가 없어서 ForeignKey("ref_maps.uuid") 같은
# 문자열 참조를 쓰면 SQLAlchemy가 flush 시점에 그 테이블을 못 찾아 에러가 난다.


class Match(Base):
    __tablename__ = "matches"

    match_id = Column(String(64), primary_key=True)
    map_uuid = Column(String(64), nullable=True)
    mode = Column(String(30), nullable=True)
    game_start = Column(DateTime, nullable=True)
    team_a_id = Column(String(64), nullable=True)
    team_b_id = Column(String(64), nullable=True)
    winner_team_id = Column(String(64), nullable=True)
    rounds_won_a = Column(Integer, nullable=True)
    rounds_won_b = Column(Integer, nullable=True)
    round_detail_json = Column(JSON, nullable=True)
    api_source = Column(String(30), nullable=True)
    collected_at = Column(DateTime, server_default=func.now())
