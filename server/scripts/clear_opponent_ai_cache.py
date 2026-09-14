"""
AI 리포트(상대팀 인사이트, 승부예측 탭) 캐시 1회성 삭제 스크립트.

services/opponent_ai_report.py의 strengths/weaknesses/tactic을 통문장 string에서
{stat,title,detail} 객체로 구조화하면서(scripts/clear_ai_cache.py와
동일한 이유), insights 테이블에 이미 저장돼 있던 구버전 캐시는 stat/title이 빈
값으로 읽힌다(_decode_item/_decode_tactic의 레거시 호환 경로). 화면에 새 카드 UI
(AiReportCard 재사용)가 반영되게 하려면 캐시를 지워 Claude가 새 스키마로 다시
생성하도록 유도해야 한다.

opponent_team_id IS NOT NULL 조건은 services/opponent_ai_report.py::_save_report/
_read_cached_report와 동일 - "승부예측 > AI 리포트"(상대팀 매치업) insights만
대상으로 하고, scripts/clear_ai_cache.py가 담당하는 "우리팀 분석" 팀 단위
insights(opponent_team_id IS NULL)는 건드리지 않는다.
"""
from database.connection import SessionLocal
from models.insight import Insight


def clear_opponent_ai_report_cache():
    db = SessionLocal()
    try:
        deleted = (
            db.query(Insight)
            .filter(Insight.opponent_team_id.isnot(None))
            .delete()
        )
        db.commit()
        print(f"삭제된 행: {deleted}")
    finally:
        db.close()


if __name__ == "__main__":
    clear_opponent_ai_report_cache()
