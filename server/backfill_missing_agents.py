"""
match_player_stats.agent_uuid가 NULL인 과거 매치들을 다시 채우는 1회성 백필 스크립트.

원인: ref_agents 테이블이 나중에 갱신되기 전(신규 요원 미등록 시점 등)에 저장된 매치는
agent_uuid를 못 찾아 NULL로 남는다(services/match_sync.py::_insert_match, services/
match_history.py::upsert_match_history 둘 다 agent_meta.get(character.lower())가
None이면 그대로 NULL을 저장하는 구조 - 정상 동작이지만 과거 데이터는 소급 갱신이 안 됨).

새 파싱 로직을 따로 만들지 않고, 이미 검증된 services/match_history.py::
upsert_match_history를 그대로 재사용해 다시 저장한다 - 그래야 이후 다른 필드(KAST,
first_bloods 등) 계산 로직과도 항상 같은 소스를 쓰게 된다.
"""
import asyncio

from database.connection import SessionLocal
from sqlalchemy import text

from services import henrik_api
from services.match_history import upsert_match_history


async def backfill():
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT DISTINCT match_id FROM match_player_stats WHERE agent_uuid IS NULL")
        ).fetchall()
        match_ids = [r[0] for r in rows]
        print(f"대상 매치 {len(match_ids)}건")

        for match_id in match_ids:
            try:
                match = await henrik_api.get_match_detail(match_id)
            except henrik_api.HenrikRateLimitError:
                print(f"레이트리밋 - 중단, 남은 매치는 다음 실행에서 이어서 처리: {match_id}")
                break
            if not match:
                print(f"스킵(응답 없음): {match_id}")
                continue
            upsert_match_history(db, match_id, match)
            print(f"완료: {match_id}")
    finally:
        await henrik_api.aclose_client()
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill())