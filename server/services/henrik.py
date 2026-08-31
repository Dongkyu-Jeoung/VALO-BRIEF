"""
HenrikDev(Valorant 비공식 API) 연동.
DB에 아직 없는 개인/팀을 검색했을 때, 실제로 존재하는 Riot 계정/프리미어 팀인지
확인하기 위한 최소한의 클라이언트 연동
"""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

HENRIK_API_BASE_URL = "https://api.henrikdev.xyz"
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY")

_HEADERS = {"Authorization": HENRIK_API_KEY} if HENRIK_API_KEY else {}
_TIMEOUT = 5.0


async def _get(path: str) -> dict | None:
    """성공(200)이면 응답의 data, 존재하지 않음(404) 등은 None."""
    url = f"{HENRIK_API_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            res = await client.get(url, headers=_HEADERS)
        except httpx.HTTPError:
            # 네트워크/타임아웃 등 - 존재 여부를 확정할 수 없으므로 미존재로 간주
            return None

    if res.status_code != 200:
        return None

    return res.json().get("data")


async def get_account(riot_name: str, riot_tag: str) -> dict | None:
    """Riot ID(name#tag) 계정 조회. v1/account 사용 (v2는 매치 기록이 없는
    계정에서 404(code 24, match data 없음)를 내려줘 신규 계정 오탐 가능성이 있음)."""
    return await _get(f"/valorant/v1/account/{riot_name}/{riot_tag}")


async def get_premier_team(team_name: str, team_tag: str) -> dict | None:
    """팀명#태그로 프리미어 팀 조회."""
    return await _get(f"/valorant/v1/premier/{team_name}/{team_tag}")
