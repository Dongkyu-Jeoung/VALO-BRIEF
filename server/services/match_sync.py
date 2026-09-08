from sqlalchemy.orm import Session

from database.connection import SessionLocal
from ml.engagement_predictor import RECENT_MATCHES
from services import henrik_api, match_history


async def _sync(db: Session, team_name: str, team_tag: str) -> None:
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:RECENT_MATCHES] if m.get("id")]

    for match_id in match_ids:
        try:
            match = await henrik_api.get_match_detail(match_id)
        except henrik_api.HenrikRateLimitError:
            # 남은 매치는 이 팀이 다음에 페이지 조회로 자연스럽게 이어서 채워진다.
            break
        if not match:
            continue

        try:
            match_history.upsert_match_history(db, match_id, match)
        except Exception as e:
            db.rollback()
            print(f"  [match_sync] upsert 실패(match_id={match_id}): {e}")


async def sync_team_match_history(team_name: str, team_tag: str) -> None:
    """회원가입 직후 routers/auth.py가 BackgroundTasks로 실행하는 진입점.
    Depends(get_db) 세션은 요청 생명주기에 묶여 있어 백그라운드 태스크에서 재사용할 수
    없으므로 여기서 별도 세션을 열고 닫는다."""
    db = SessionLocal()
    try:
        await _sync(db, team_name, team_tag)
    finally:
        db.close()
