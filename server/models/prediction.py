"""
predictions 테이블 ORM 모델 (승부 예측 결과, Layer1). database/valo_brief.sql 참고.
routers/predict.py에서 예측할 때마다 한 행씩 저장한다.

team_b_id(상대팀)는 상대가 이 서비스에 가입한 계정일 때만 채워지는 선택적 FK -
opponent_team_name/opponent_team_tag가 가입 여부와 무관하게 항상 상대팀을 식별한다.
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from database.connection import Base
from models.team import Team


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id = Column(Integer, primary_key=True, autoincrement=True)
    team_a_id = Column(String(64), ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    team_b_id = Column(String(64), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    opponent_team_name = Column(String(50), nullable=False)
    opponent_team_tag = Column(String(10), nullable=False)
    map_uuid = Column(String(64), nullable=True)
    predicted_winrate_a = Column(Float, nullable=False)
    predicted_winrate_b = Column(Float, nullable=False)
    model_version = Column(String(30), nullable=False)
    feature_snapshot_json = Column(JSON, nullable=True)
    actual_result = Column(String(10), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # 두 FK가 같은 테이블(teams)을 가리켜서 foreign_keys를 명시해야 함. 문자열("Team")
    # 대신 클래스를 직접 참조 - Team이 다른 곳에서 먼저 import되어 있어야만 매퍼가
    # 이름을 풀 수 있는 문자열 방식의 import-order 의존성을 없앤다.
    team_a = relationship(Team, foreign_keys=[team_a_id])
    team_b = relationship(Team, foreign_keys=[team_b_id])
