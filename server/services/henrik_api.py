"""
HenrikDev(Valorant 비공식 API) 연동.
DB에 아직 없는 개인/팀을 검색했을 때, 실제로 존재하는 Riot 계정/프리미어 팀인지
확인하기 위한 최소한의 클라이언트 연동
"""
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

# 같은 (경로+파라미터) 응답을 짧은 시간 안에 재요청하는 경우가 많다
# (예: 검색 직후 프로필 진입, 리액트 재렌더/새로고침, 인기 선수/팀 중복 조회 등).
# 성공(200) 응답만 짧게 캐싱해서 그 구간의 재요청은 네트워크 왕복 없이 즉시 반환한다.
_CACHE_TTL_SECONDS = 60
_response_cache: dict[str, tuple[float, dict | list | None]] = {}


def _cache_key(path: str, params: dict | None) -> str:
    if not params:
        return path
    return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))

# 요청마다 AsyncClient를 새로 만들면 매번 TCP+TLS 핸드셰이크가 발생해 호출당
# 1~2초씩 더 걸린다 (실측: 새 클라이언트 1.4s대 vs 재사용 커넥션 0.3s대).
# 프로세스 생존 기간 동안 커넥션 풀을 유지하는 클라이언트 하나를 재사용한다.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=HENRIK_API_BASE_URL, headers=_HEADERS, timeout=_TIMEOUT)
    return _client


async def aclose_client() -> None:
    """FastAPI shutdown 시 호출 - 열려있는 커넥션 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    """성공(200)이면 응답의 data, 존재하지 않음(404) 등은 None.
    성공 응답은 _CACHE_TTL_SECONDS 동안 캐싱해 동일 요청의 중복 호출을 막는다."""
    key = _cache_key(path, params)
    cached = _response_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    client = _get_client()
    try:
        res = await client.get(path, params=params)
    except httpx.HTTPError:
        # 네트워크/타임아웃 등 - 존재 여부를 확정할 수 없으므로 미존재로 간주
        return None

    if res.status_code != 200:
        return None

    value = res.json().get("data")
    _response_cache[key] = (time.monotonic(), value)
    return value


# Riot ID(name#tag) 계정 조회. v2 하나로 통일 (기존엔 검색 존재확인=v1, 프로필=v2로 나뉘어
# 같은 계정을 두 번 조회했음). v2는 v1 상위 호환이라 puuid/region/account_level에 더해
# title/platforms(콘솔 지원)까지 한 번에 준다.
# 알려진 제약: 매치 기록이 전혀 없는 계정은 Henrik이 404(code 24, "match data 없음")를
# 내려줘 존재하는 계정도 미존재로 보일 수 있다 (실제 API로 직접 확인한 케이스).
async def get_account(riot_name: str, riot_tag: str) -> dict | None:
    return await _get(f"/valorant/v2/account/{riot_name}/{riot_tag}")

# 팀명#태그로 프리미어 팀 조회
async def get_premier_team(team_name: str, team_tag: str) -> dict | None:
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}")


# 현재 랭크/RR 조회 (플랫폼 지원 v3)
async def get_mmr(region: str, platform: str, riot_name: str, riot_tag: str) -> dict | None:
    return await _get(f"/valorant/v3/mmr/{region}/{platform}/{riot_name}/{riot_tag}")


# 최근 매치 리스트 (플랫폼 지원 v4, 라운드/킬/스탯 포함)
async def get_matches(
    region: str,
    platform: str,
    riot_name: str,
    riot_tag: str,
    size: int = 20,
    mode: str | None = None,
) -> list | None:
    params: dict = {"size": size}
    if mode:
        params["mode"] = mode
    return await _get(f"/valorant/v4/matches/{region}/{platform}/{riot_name}/{riot_tag}", params=params)
