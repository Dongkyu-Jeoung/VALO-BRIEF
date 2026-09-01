"""
HenrikDev(Valorant 비공식 API) 연동.
DB에 아직 없는 개인/팀을 검색했을 때, 실제로 존재하는 Riot 계정/프리미어 팀인지
확인하기 위한 최소한의 클라이언트 연동
"""
import os
import httpx
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

HENRIK_API_BASE_URL = "https://api.henrikdev.xyz"
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")

_HEADERS = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
_TIMEOUT = 5.0


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    """성공(200)이면 응답의 data, 존재하지 않음(404) 등은 None."""
    url = f"{HENRIK_API_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            res = await client.get(url, headers=_HEADERS, params=params)
        except httpx.HTTPError:
            # 네트워크/타임아웃 등 - 존재 여부를 확정할 수 없으므로 미존재로 간주
            return None

    if res.status_code != 200:
        return None

    return res.json().get("data")


# Riot ID(name#tag) 계정 조회. v1/account 사용 (search.py 캐시-어사이드 검증용)
async def get_account(riot_name: str, riot_tag: str) -> dict | None:
    return await _get(f"/valorant/v1/account/{riot_name}/{riot_tag}")

# 팀명#태그로 프리미어 팀 조회
async def get_premier_team(team_name: str, team_tag: str) -> dict | None:
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}")


# Riot ID(name#tag) 계정 조회. v2 - v1 상위 호환(콘솔 계정 지원), 프로필 화면(레벨/칭호/카드)용
async def get_account_v2(riot_name: str, riot_tag: str) -> dict | None:
    return await _get(f"/valorant/v2/account/{riot_name}/{riot_tag}")


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
