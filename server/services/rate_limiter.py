"""
Henrik API 키별 요청 제한. 같은 키는 같은 RateLimiter 인스턴스를 공유한다.
서로 다른 키는 요청 기록과 429 대기 상태를 분리한다.

스레드 안전성: 이벤트 루프 스레드와 워커 스레드가 동시에 이 상태를 건드릴 수 있어
threading.Lock으로 보호한다. 잠금을 쥔 채로 대기(sleep)하지 않고, 얼마나 기다려야
하는지만 계산해서 반환한 뒤 잠금을 풀고 각자의 방식(asyncio.sleep 또는 time.sleep)으로
기다린다 - 그래야 대기 중에도 다른 스레드가 카운터를 확인할 수 있다.
"""
import asyncio
import re
import threading
import time
from collections import deque
from email.utils import parsedate_to_datetime
from math import isfinite

RATE_WINDOW_SECONDS = 60.0


def retry_after_seconds(headers, default=RATE_WINDOW_SECONDS):
    """서버의 대기 시간을 초로 해석한다. 긴 대기 시간을 임의로 줄이지 않는다."""
    headers = {key.lower(): value for key, value in headers.items()}
    delays = []
    raw = headers.get("retry-after")
    if raw is not None:
        try:
            delays.append(float(raw))
        except (TypeError, ValueError):
            try:
                delays.append(parsedate_to_datetime(raw).timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                pass
    # Henrik의 다중 구간 헤더에서 소진된 버킷의 가장 긴 대기를 따른다.
    for bucket in headers.get("ratelimit", "").split(","):
        params = dict(re.findall(r';\s*([rt])\s*=\s*([0-9.+-]+)', bucket))
        try:
            if float(params["r"]) <= 0:
                delays.append(float(params["t"]))
        except (KeyError, ValueError):
            pass
    try:
        reset = float(headers["x-ratelimit-reset"])
        # 기존 초 단위 헤더와 Unix timestamp 형식을 모두 처리한다.
        delays.append(reset - time.time() if reset >= 1_000_000_000 else reset)
    except (KeyError, TypeError, ValueError):
        pass
    valid = [delay for delay in delays if isfinite(delay) and delay > 0]
    return max(valid) if valid else default


class RateLimiter:
    def __init__(self, requests_per_minute):
        self.requests_per_minute = requests_per_minute
        self._request_times: deque[float] = deque()
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def defer_requests(self, seconds):
        if not isfinite(seconds) or seconds <= 0:
            seconds = RATE_WINDOW_SECONDS
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def register_rate_limit(self, headers):
        delay = retry_after_seconds(headers) + 0.05
        self.defer_requests(delay)
        return delay

    def _record_or_wait_seconds(self):
        """여유가 있으면 요청을 기록하고, 없으면 다시 확인할 때까지의 대기를 반환한다."""
        with self._lock:
            now = time.monotonic()
            if now < self._blocked_until:
                return self._blocked_until - now
            while self._request_times and now - self._request_times[0] > RATE_WINDOW_SECONDS:
                self._request_times.popleft()
            if len(self._request_times) >= self.requests_per_minute:
                return RATE_WINDOW_SECONDS - (now - self._request_times[0]) + 0.05
            self._request_times.append(now)
            return 0.0

    async def throttle_async(self):
        while True:
            wait = self._record_or_wait_seconds()
            if wait <= 0:
                return
            await asyncio.sleep(wait)

    def throttle_sync(self):
        while True:
            wait = self._record_or_wait_seconds()
            if wait <= 0:
                return
            time.sleep(wait)
