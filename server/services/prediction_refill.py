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
MAX_RATE_LIMIT_RETRIES = 3
_tasks: dict[str, asyncio.Task] = {}
_next_attempt: OrderedDict[str, float] = OrderedDict()
_worker_lock = asyncio.Lock()


async def _fetch_with_retry(fetch, checkpoint):
    """실패한 API 조회만 재시도한다. 추가 재시도 대기 중 작업 잠금을 반환한다."""
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            async with _worker_lock:
                return await fetch()
        except henrik_api.HenrikRateLimitError as exc:
            if attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            wait = max(exc.retry_after, 60.0 * (2 ** attempt))
            checkpoint(f"[DB REFILL] 429 대기: {wait:.2f}s, 재시도={attempt + 1}/{MAX_RATE_LIMIT_RETRIES}")
            await asyncio.sleep(wait)


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
    history = await _fetch_with_retry(
        lambda: henrik_api.get_premier_team_history(team_name, team_tag), checkpoint)
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
        match = await _fetch_with_retry(lambda: henrik_api.get_match_detail(match_id), checkpoint)
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
        # 서로 다른 팀이 같은 경기를 보완할 때 저장 작업이 겹치지 않도록 한다.
        async with _worker_lock:
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
    next_attempt = _next_attempt.get(team_id)
    if next_attempt is not None and time.monotonic() < next_attempt:
        checkpoint("[DB REFILL] 재시도 대기 시간 이내: 생략")
        return

    async def run():
        cooldown = RETRY_INTERVAL_SECONDS
        try:
            await refill(team_id, team_name, team_tag, list(dict.fromkeys(puuids)), checkpoint)
        except asyncio.CancelledError:
            cooldown = None
            checkpoint("[DB REFILL] 서버 종료 등으로 취소됨")
            raise
        except henrik_api.HenrikRateLimitError as exc:
            cooldown = max(exc.retry_after, 60.0)
            checkpoint(f"[DB REFILL] 429 재시도 소진: 중단, {cooldown:.2f}s 이후 예측 요청에서 재예약 가능")
            logger.warning("Prediction DB refill rate limited for team %s; retry eligible in %.2fs",
                           team_id, cooldown)
        except Exception as exc:
            checkpoint(f"[DB REFILL] 실패: {type(exc).__name__}")
            logger.exception("Prediction DB refill failed for team %s", team_id)
        finally:
            _tasks.pop(team_id, None)
            if cooldown is not None:
                _next_attempt[team_id] = time.monotonic() + cooldown
                _next_attempt.move_to_end(team_id)
                while len(_next_attempt) > 256:
                    _next_attempt.popitem(last=False)

    _tasks[team_id] = asyncio.create_task(run())
    checkpoint(f"[DB REFILL] 백그라운드 예약: 부족 선수={len(set(puuids))}")
