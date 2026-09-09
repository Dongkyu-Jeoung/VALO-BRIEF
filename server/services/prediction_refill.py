"""예측 응답 이후 우리 팀 경기 DB를 보완한다. 프로세스 내 중복 작업을 합친다."""
import asyncio
import logging
import time
from collections import OrderedDict

from database.connection import SessionLocal
from ml.predictor import _db_player_feature
from services import henrik_api, match_history

logger = logging.getLogger(__name__)
MAX_MATCHES = 20
RETRY_INTERVAL_SECONDS = 20 * 60
_tasks: dict[str, asyncio.Task] = {}
_last_attempt: OrderedDict[str, float] = OrderedDict()
_worker_lock = asyncio.Lock()


def _remaining(puuids):
    with SessionLocal() as db:
        return [puuid for puuid in puuids if _db_player_feature(db, puuid) is None]


def _store(match_id, match, started_at):
    with SessionLocal() as db:
        match_history.upsert_match_history(db, match_id, match, started_at)


async def refill(team_id, team_name, team_tag, puuids, checkpoint):
    remaining = await asyncio.to_thread(_remaining, puuids)
    if not remaining:
        checkpoint("[DB REFILL] 이미 충족: 보완 생략")
        return
    checkpoint(f"[DB REFILL] 시작: 부족 선수={len(remaining)}, 최대 {MAX_MATCHES}경기 탐색")
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    recent = sorted((history or {}).get("league_matches") or [],
                    key=lambda row: row.get("started_at") or "", reverse=True)
    seen = set()
    for row in recent:
        match_id = row.get("id")
        if not match_id or match_id in seen:
            continue
        if len(seen) >= MAX_MATCHES:
            break
        seen.add(match_id)
        match = await henrik_api.get_match_detail(match_id)
        if not match or (match.get("metadata") or {}).get("matchid") != match_id:
            checkpoint(f"[DB REFILL] 경기 응답 없음/불일치: {match_id}")
            continue
        rosters = [(match.get("teams", {}).get(side) or {}).get("roster") or {}
                   for side in ("red", "blue")]
        if not any(str(r.get("name", "")).strip().lower() == team_name.strip().lower()
                   and str(r.get("tag", "")).strip().lower() == team_tag.strip().lower()
                   for r in rosters):
            checkpoint(f"[DB REFILL] 팀 불일치: {match_id}")
            continue
        await asyncio.to_thread(_store, match_id, match, row.get("started_at"))
        remaining = await asyncio.to_thread(_remaining, remaining)
        checkpoint(f"[DB REFILL] 경기 저장: {match_id}, 부족 선수={len(remaining)}")
        if not remaining:
            break
    checkpoint(f"[DB REFILL] 종료: 조회 경기={len(seen)}, 미충족 선수={len(remaining)}")


def schedule_refill(team_id, team_name, team_tag, puuids, checkpoint):
    """이벤트 루프에서 호출. ORM 객체/요청 세션은 작업에 전달하지 않는다."""
    if not puuids:
        return
    if team_id in _tasks:
        checkpoint("[DB REFILL] 동일 팀 작업 진행 중: 중복 생략")
        return
    last = _last_attempt.get(team_id)
    if last is not None and time.monotonic() - last < RETRY_INTERVAL_SECONDS:
        checkpoint("[DB REFILL] 재시도 간격 20분 이내: 생략")
        return

    async def run():
        try:
            # 여러 팀이 한꺼번에 새 API 요청을 쏟아내지 않도록 직렬 실행한다.
            async with _worker_lock:
                await refill(team_id, team_name, team_tag, list(dict.fromkeys(puuids)), checkpoint)
        except asyncio.CancelledError:
            checkpoint("[DB REFILL] 서버 종료 등으로 취소됨")
            raise
        except Exception as exc:
            checkpoint(f"[DB REFILL] 실패: {type(exc).__name__}")
            logger.exception("Prediction DB refill failed for team %s", team_id)
        finally:
            _tasks.pop(team_id, None)
            _last_attempt[team_id] = time.monotonic()
            _last_attempt.move_to_end(team_id)
            while len(_last_attempt) > 256:
                _last_attempt.popitem(last=False)

    _tasks[team_id] = asyncio.create_task(run())
    checkpoint(f"[DB REFILL] 백그라운드 예약: 부족 선수={len(set(puuids))}")
