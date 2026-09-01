"""
HenrikDev(Valorant 비공식 API) 클라이언트.
계정/팀 존재 확인, 랭크, 매치 이력 조회에 필요한 최소한의 엔드포인트만 감싼다.
"""
import asyncio
import os
import time
import httpx
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

HENRIK_API_BASE_URL = "https://api.henrikdev.xyz"
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")

_HEADERS = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
_TIMEOUT = 5.0

# 같은 (경로+파라미터) 요청을 짧은 시간 안에 다시 받는 경우가 많다(검색 직후 프로필 진입,
# Act 탭 전환 등). 성공(200) 응답만 짧게 캐싱해 그 구간의 재요청은 네트워크 없이 즉시 반환한다.
_CACHE_TTL_SECONDS = 60
_response_cache: dict[str, tuple[float, dict | list | None]] = {}

# 캐시가 아직 없는 상태에서 같은 요청이 겹치는 경우(백그라운드 프리페치와 실제 요청이
# 거의 동시에 들어옴)를 위한 in-flight 공유. 진행 중인 동일 요청이 있으면 새로 부르지 않고
# 그 결과를 같이 기다린다.
_inflight: dict[str, asyncio.Future] = {}

# 요청마다 새 AsyncClient를 만들면 매번 TCP+TLS 핸드셰이크가 발생해 호출당 1~2초씩 더 든다.
# 프로세스 생존 기간 동안 커넥션 풀을 유지하는 클라이언트 하나를 재사용한다.
_client: httpx.AsyncClient | None = None


def _cache_key(path: str, params: dict | None) -> str:
    """경로+파라미터를 캐시/in-flight 딕셔너리의 키 문자열로 정규화."""
    if not params:
        return path
    return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


def _get_client() -> httpx.AsyncClient:
    """프로세스 전역에서 재사용하는 커넥션 풀 클라이언트를 반환(없으면 생성)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=HENRIK_API_BASE_URL, headers=_HEADERS, timeout=_TIMEOUT)
    return _client


async def aclose_client() -> None:
    """FastAPI shutdown 훅에서 호출 - 열려있는 커넥션 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    """GET 요청 공통 진입점. 성공(200)이면 응답의 data, 실패/404 등은 None.
    성공 응답은 TTL 캐싱하고, 캐시가 없는 상태에서 겹치는 요청은 in-flight로 공유한다."""
    key = _cache_key(path, params)
    cached = _response_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    existing = _inflight.get(key)
    if existing is not None:
        return await existing

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _inflight[key] = future
    try:
        client = _get_client()
        try:
            res = await client.get(path, params=params)
        except httpx.HTTPError:
            # 네트워크/타임아웃 등 - 존재 여부를 확정할 수 없으므로 미존재로 간주
            value = None
        else:
            value = res.json().get("data") if res.status_code == 200 else None

        if value is not None:
            _response_cache[key] = (time.monotonic(), value)
        future.set_result(value)
        return value
    finally:
        _inflight.pop(key, None)


async def get_account(riot_name: str, riot_tag: str) -> dict | None:
    """Riot ID(name#tag) 계정 조회 (v2 - puuid/region/account_level/title 포함).
    매치 기록이 전혀 없는 계정은 Henrik이 404를 내려줘 존재해도 미존재로 보일 수 있음(알려진 제약)."""
    return await _get(f"/valorant/v2/account/{riot_name}/{riot_tag}")


async def get_premier_team(team_name: str, team_tag: str) -> dict | None:
    """팀명#태그로 프리미어 팀 조회."""
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}")


async def get_mmr(region: str, platform: str, riot_name: str, riot_tag: str) -> dict | None:
    """현재 랭크/RR 조회."""
    return await _get(f"/valorant/v3/mmr/{region}/{platform}/{riot_name}/{riot_tag}")


async def get_mmr_history(region: str, riot_name: str, riot_tag: str) -> dict | None:
    """Act별 최종/최고 티어 이력 조회. by_season 딕셔너리가 "e11a5" 같은 Riot 공식
    Episode/Act 키로 최종 티어와 승패 판수를 준다 - Act별 랭크는 매치 목록이 아니라 이 값을 쓴다."""
    return await _get(f"/valorant/v2/mmr/{region}/{riot_name}/{riot_tag}")


async def get_stored_matches(region: str, riot_name: str, riot_tag: str, mode: str | None = None) -> list | None:
    """Henrik이 미리 캐싱해둔 매치 이력 조회 (라운드/킬/좌표 상세 없는 경량 요약, 조회 대상
    플레이어 관점이라 참가자 목록 검색 불필요). mode 없이 부르면 전체 모드가 섞여 최근순으로
    잘리는데, 이 과정에서 플레이 빈도가 낮은 모드(대개 경쟁전)가 결과에서 빠질 수 있어
    호출부에서 무필터 + mode="competitive" 두 번을 합쳐 쓴다."""
    params = {"mode": mode} if mode else None
    return await _get(f"/valorant/v1/stored-matches/{region}/{riot_name}/{riot_tag}", params=params)
