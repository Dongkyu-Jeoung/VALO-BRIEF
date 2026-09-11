"""
AI 리포트(팀 전술 리포트) 캐시 1회성 삭제 스크립트.

services/ai_report.py의 strengths/weaknesses/playerFeedback.strength/weakness를
통문장 string에서 {stat,title,detail} 객체로 구조화하면서, insights 테이블에 이미
저장돼 있던 구버전 캐시는 stat/title이 빈 값으로 읽힌다(_decode_item의 레거시
호환 경로). 화면에 새 카드 UI가 반영되게 하려면 캐시를 지워 Claude가 새 스키마로
다시 생성하도록 유도해야 한다.

opponent_team_id IS NULL 조건은 services/ai_report.py::_save_report/
_read_cached_report와 동일 - "우리팀 분석 > AI 리포트" 탭용 팀 단위 인사이트만
대상으로 하고, 상대팀 전적 검색 등 다른 용도의 insights 행은 건드리지 않는다.
"""
from database.connection import SessionLocal
from models.insight import Insight


def clear_ai_report_cache():
    db = SessionLocal()
    try:
        deleted = (
            db.query(Insight)
            .filter(Insight.opponent_team_id.is_(None))
            .delete()
        )
        db.commit()
        print(f"삭제된 행: {deleted}")
    finally:
        db.close()


if __name__ == "__main__":
    clear_ai_report_cache()