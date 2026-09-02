"""
valorant-api.com 클라이언트. 인증 불필요(공개 API). 플레이어 카드/칭호처럼 개수가 많아
DB에 전량 시드하기 어려운 참조 데이터를 uuid 단위로 그때그때 조회할 때 쓴다
(services/cosmetics.py가 결과를 캐싱).
"""
import httpx

VALORANT_API_BASE_URL = "https://valorant-api.com/v1"
_TIMEOUT = 5.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=VALORANT_API_BASE_URL, timeout=_TIMEOUT)
    return _client


async def aclose_client() -> None:
    """FastAPI shutdown 훅에서 호출 - 열려있는 커넥션 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(path: str) -> dict | None:
    try:
        res = await _get_client().get(path, params={"language": "ko-KR"})
    except httpx.HTTPError:
        return None
    if res.status_code != 200:
        return None
    return res.json().get("data")


async def get_player_card(uuid: str) -> dict | None:
    """플레이어 카드 조회 - displayName(한글), displayIcon(아바타용 이미지 URL) 등."""
    return await _get(f"/playercards/{uuid}")


async def get_player_title(uuid: str) -> dict | None:
    """플레이어 칭호 조회 - titleText(한글). 이미지는 없음(발로란트 자체가 텍스트 전용 요소)."""
    return await _get(f"/playertitles/{uuid}")
