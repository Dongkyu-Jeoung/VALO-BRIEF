"""Process-local cache of successful Premier prediction responses."""
import asyncio
import logging
from collections import OrderedDict
from copy import deepcopy
from time import monotonic

TTL_SECONDS = 40 * 60
MAX_ENTRIES = 256
_results = OrderedDict()
_inflight = {}
logger = logging.getLogger(__name__)


async def _compute(key, factory, ttl_seconds):
    try:
        result = await factory()
        _results[key] = (monotonic() + ttl_seconds, deepcopy(result))
        _results.move_to_end(key)
        while len(_results) > MAX_ENTRIES:
            _results.popitem(last=False)
        return result
    finally:
        _inflight.pop(key, None)


def _consume_exception(task):
    # A computation can finish after all HTTP callers have disconnected.
    if not task.cancelled():
        task.exception()


async def get_or_create(key, factory, ttl_seconds=TTL_SECONDS):
    """Share concurrent requests; TTL starts on success and never slides on hits."""
    now = monotonic()
    for expired in [k for k, (deadline, _) in _results.items() if deadline <= now]:
        del _results[expired]
    cached = _results.get(key)
    if cached is not None:
        _results.move_to_end(key)
        logger.info("[PREDICTION CACHE] HIT key=%s", key)
        return deepcopy(cached[1])

    task = _inflight.get(key)
    if task is None:
        logger.info("[PREDICTION CACHE] MISS key=%s", key)
        task = asyncio.create_task(_compute(key, factory, ttl_seconds))
        _inflight[key] = task
        task.add_done_callback(_consume_exception)
    else:
        logger.info("[PREDICTION CACHE] SHARED key=%s", key)
    # One caller cancelling must not cancel the prediction for other callers.
    return deepcopy(await asyncio.shield(task))
