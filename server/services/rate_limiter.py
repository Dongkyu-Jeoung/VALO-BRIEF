"""
Henrik API 요청 속도 제한 - 공유 카운터.

services/henrik_api.py(비동기, 이벤트 루프에서 직접 실행)와 ml/valorant_git.py(동기,
asyncio.to_thread로 별도 워커 스레드에서 실행)가 같은 HENRIK_API_KEY의 같은 요청 버킷을
나눠 쓰면서도 각자 독립된 throttle 카운터를 갖고 있었다 - 그래서 한쪽이 "나는 분당 28건
이하로 보낸다"고 안심해도, 둘이 동시에 트래픽을 보내면 실제 Henrik 쪽 30/분 한도를 합쳐서
넘겨 429를 받을 수 있었다(승부예측_성능_분석.md 3번 참고). 요청 타임스탬프 상태를 이
모듈 하나로 통합해서 두 호출부가 실제로 같은 예산을 나눠 쓰게 한다.

스레드 안전성: 이벤트 루프 스레드와 워커 스레드가 동시에 이 상태를 건드릴 수 있어
threading.Lock으로 보호한다. 잠금을 쥔 채로 대기(sleep)하지 않고, 얼마나 기다려야
하는지만 계산해서 반환한 뒤 잠금을 풀고 각자의 방식(asyncio.sleep 또는 time.sleep)으로
기다린다 - 그래야 대기 중에도 다른 스레드가 카운터를 확인할 수 있다.
"""
import asyncio
import threading
import time
from collections import deque

# Henrik 키 실측 한도(응답 헤더 기준 "per1min";q=30, 분당 30건)보다 살짝 낮게 잡아
# 우리 쪽에서 먼저 속도를 늦춘다.
RATE_LIMIT_PER_MIN = 28
RATE_WINDOW_SECONDS = 60.0

_request_times: deque[float] = deque()
_lock = threading.Lock()


def _record_or_wait_seconds() -> float:
    """지금 요청 1건을 보내도 되면 바로 기록하고 0.0을 반환. 한도를 넘었으면 기록하지
    않고 얼마나 기다려야 다시 확인하면 되는지(초)를 반환한다 - 호출부가 그만큼 기다린 뒤
    다시 불러야 한다(대기 중 다른 스레드가 먼저 자리를 차지했을 수 있으므로 한 번에
    확정하지 않고 재확인 루프를 돈다)."""
    with _lock:
        now = time.monotonic()
        while _request_times and now - _request_times[0] > RATE_WINDOW_SECONDS:
            _request_times.popleft()
        if len(_request_times) >= RATE_LIMIT_PER_MIN:
            return RATE_WINDOW_SECONDS - (now - _request_times[0]) + 0.05
        _request_times.append(now)
        return 0.0


async def throttle_async() -> None:
    """이벤트 루프(services/henrik_api.py)에서 쓰는 버전 - 기다리는 동안 다른 코루틴은
    계속 돈다."""
    while True:
        wait = _record_or_wait_seconds()
        if wait <= 0:
            return
        await asyncio.sleep(wait)


def throttle_sync() -> None:
    """워커 스레드(ml/valorant_git.py, asyncio.to_thread로 실행됨)에서 쓰는 버전 - 그
    스레드만 블록되고 이벤트 루프는 막지 않는다."""
    while True:
        wait = _record_or_wait_seconds()
        if wait <= 0:
            return
        time.sleep(wait)
