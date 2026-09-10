"""
HenrikDev(Valorant 비공식 API) 클라이언트.
계정/팀 존재 확인, 랭크, 매치 이력 조회에 필요한 최소한의 엔드포인트만 감싼다.
"""
import asyncio
import logging
import time
import httpx
from services.henrik_config import GENERAL as _API

logger = logging.getLogger(__name__)

HENRIK_API_BASE_URL = "https://api.henrikdev.xyz"
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


class HenrikRateLimitError(Exception):
    """Henrik API 레이트리밋(429)에 계속 걸렸을 때 - "존재하지 않음"(None)과 반드시
    구분해야 한다. 예전엔 429도 다른 실패와 똑같이 None으로 뭉뚱그려 반환했는데, 그게
    /exists 응답에서 "존재하지 않는 팀/선수"와 동일하게 처리돼 - 실제로는 존재하는 팀인데
    검색이 갑자기 안 되는 것처럼 보이는 버그의 원인이었다(팀 검색 1건이 exists 확인 +
    백그라운드 프리페치(이력+매치상세 최대 10건)까지 겹쳐 최대 12개 요청을 짧은 시간에
    쓰므로 다른 화면 요청과 합쳐 API 키 한도를 초과할 수 있다).
    main.py의 전역 예외 핸들러가 이걸 잡아 503으로 응답한다."""

    def __init__(self, path, retry_after=60.0):
        super().__init__(path)
        self.retry_after = retry_after


# 검색·프로필·팀 로스터·DB 보완은 일반 키의 예산을 공유한다.


def _cache_key(path: str, params: dict | None) -> str:
    """경로+파라미터를 캐시/in-flight 딕셔너리의 키 문자열로 정규화."""
    if not params:
        return path
    return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


def _get_client() -> httpx.AsyncClient:
    """프로세스 전역에서 재사용하는 커넥션 풀 클라이언트를 반환(없으면 생성)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=HENRIK_API_BASE_URL, headers=_API.headers, timeout=_TIMEOUT)
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
        await _get_uncached("/valorant/v1/status/kr", None)
    except (httpx.HTTPError, HenrikRateLimitError):
        pass


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    """GET 요청 공통 진입점. 성공(200)이면 응답의 data, 404 등 확정적 실패는 None.
    성공 응답은 TTL 캐싱하고, 캐시가 없는 상태에서 겹치는 요청은 in-flight로 공유한다.
    429(레이트리밋)는 "존재하지 않음"과 절대 같은 값(None)으로 섞이면 안 되므로
    HenrikRateLimitError로 별도 전파한다(위 클래스 docstring 참고)."""
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
        try:
            value = await _get_uncached(path, params)
        except BaseException as exc:
            # future를 resolve하지 않고 그냥 두면 이 요청을 함께 기다리던(in-flight 공유)
            # 다른 동시 호출자가 영원히 멈춘다 - 반드시 같은 예외를 넘겨줘야 한다.
            future.set_exception(exc)
            # 아무도 이 future를 await하지 않는 경우(보통 - 공유 대기자가 없을 때) asyncio가
            # "exception was never retrieved" 경고를 남기므로, 우리가 이미 raise로 처리한다는
            # 걸 미리 확인 처리해둔다(exception()을 여러 번 호출해도 결과는 그대로 유지됨 -
            # 나중에 동시 대기자가 `await existing`해도 동일하게 예외를 받는다).
            future.exception()
            raise
        if value is not None:
            _response_cache[key] = (time.monotonic(), value)
        future.set_result(value)
        return value
    finally:
        _inflight.pop(key, None)


async def _get_uncached(path: str, params: dict | None) -> dict | list | None:
    """실제 네트워크 요청 - 429면 Retry-After만큼 한 번 기다렸다 재시도하고, 그래도
    막히면 HenrikRateLimitError를 던진다."""
    client = _get_client()
    for attempt in range(2):
        await _API.limiter.throttle_async()
        try:
            res = await client.get(path, params=params)
        except httpx.HTTPError:
            return None
        if res.status_code != 429:
            return res.json().get("data") if res.status_code == 200 else None
        wait = _API.limiter.register_rate_limit(res.headers)
        logger.warning("[HENRIK 429] key=%s async attempt=%d/2 key_wait=%.2fs", _API.name, attempt + 1, wait)
        if attempt == 1:
            raise HenrikRateLimitError(path, retry_after=wait)


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
