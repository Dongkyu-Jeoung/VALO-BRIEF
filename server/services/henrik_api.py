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


async def warm_up() -> None:
    """FastAPI startup 훅에서 호출 - 첫 실사용자 요청 전에 TCP+TLS 핸드셰이크를 미리
    끝내둔다. 안 하면 재시작 직후 첫 검색이 이 핸드셰이크 비용을 그대로 떠안는다."""
    try:
        await _get_client().get("/valorant/v1/status/kr")
    except httpx.HTTPError:
        pass


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
    """팀명#태그로 프리미어 팀 조회 (stats.wins/matches/losses, placement.division,
    customization.image 등 - 매치 상세 없이도 나오는 팀 요약 정보)."""
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}")


async def get_premier_team_history(team_name: str, team_tag: str) -> dict | None:
    """팀 최근 매치 "포인트 변동" 이력만 준다 (league_matches: [{id, points_before,
    points_after, started_at}]) - 맵/스코어/로스터는 없음. 매치별 상세가 필요하면
    여기서 얻은 match id로 get_match_detail()을 따로 불러야 한다."""
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}/history")


async def get_match_detail(match_id: str) -> dict | None:
    """매치 1건 전체 상세 (v2/match - region/platform 불필요, id만 있으면 됨).
    teams.red/blue.roster.{name,tag,members}로 어느 팀이 우리 팀인지 구분,
    players.all_players로 로스터 개인 스탯, kills로 라운드별 킬 이벤트(퍼스트블러드 계산용)를 준다.
    매치 1건이 ~1.3MB로 무거워서 여러 건을 부를 땐 반드시 asyncio.gather로 동시에 불러야 한다."""
    return await _get(f"/valorant/v2/match/{match_id}")


async def get_mmr_history(region: str, riot_name: str, riot_tag: str) -> dict | None:
    """Act별 최종/최고 티어 이력 조회. by_season 딕셔너리가 "e11a5" 같은 Riot 공식
    Episode/Act 키로 최종 티어와 승패 판수를 준다 - Act별 랭크는 매치 목록이 아니라 이 값을 쓴다.
    current_data 필드에 현재 랭크/RR도 함께 들어있어(v3/mmr과 동일 값) 별도 호출 없이 겸용한다."""
    return await _get(f"/valorant/v2/mmr/{region}/{riot_name}/{riot_tag}")


async def get_stored_matches(region: str, riot_name: str, riot_tag: str, mode: str | None = None) -> list | None:
    """Henrik이 미리 캐싱해둔 매치 이력 조회 (라운드/킬/좌표 상세 없는 경량 요약, 조회 대상
    플레이어 관점이라 참가자 목록 검색 불필요). mode 없이 부르면 저장된 전체 이력을 truncate
    없이 다 준다(total == returned로 실측 확인) 
    - mode="competitive" 등 필터는 그 전체 집합의
    부분집합이라 별도로 합칠 필요 없음(실측: 서로 다른 두 계정 모두 competitive 결과가
    무필터 결과의 완전한 부분집합이었음)."""
    params = {"mode": mode} if mode else None
    return await _get(f"/valorant/v1/stored-matches/{region}/{riot_name}/{riot_tag}", params=params)
