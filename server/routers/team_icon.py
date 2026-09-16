"""
팀 로고(Henrik team-icon) 프록시 + 캐시.
"""
import hashlib
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter(prefix="/api/team-icons", tags=["team-icons"])

_CACHE_DIR = Path(__file__).resolve().parent.parent / "static" / "team_icons"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_SOURCE_URL = "https://cdn.henrikdev.xyz/valorant/v1/premier/team-icon/{icon_uuid}"
_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _cache_path(icon_uuid: str, primary: str, secondary: str, tertiary: str) -> Path:
    digest = hashlib.sha256(f"{icon_uuid}:{primary}:{secondary}:{tertiary}".encode()).hexdigest()
    return _CACHE_DIR / f"{digest}.png"


@router.get("/{icon_uuid}")
async def get_team_icon(icon_uuid: str, primary: str = "", secondary: str = "", tertiary: str = ""):
    path = _cache_path(icon_uuid, primary, secondary, tertiary)
    if path.exists():
        return Response(content=path.read_bytes(), media_type="image/png", headers={"Cache-Control": _CACHE_CONTROL})

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(
            _SOURCE_URL.format(icon_uuid=icon_uuid),
            params={"primary": primary, "secondary": secondary, "tertiary": tertiary},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=404, detail="팀 아이콘을 찾을 수 없습니다.")

    path.write_bytes(res.content)
    return Response(content=res.content, media_type="image/png", headers={"Cache-Control": _CACHE_CONTROL})
