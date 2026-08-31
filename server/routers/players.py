from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.connection import get_db
from services import henrik_api
from services.riot_accounts import find_riot_account, upsert_riot_account
from services.player_profile import build_player_profile

router = APIRouter(prefix="/api/players", tags=["players"])

_DEFAULT_REGION = "kr"
_PLATFORM = "pc"


@router.get("/{riot_name}/{riot_tag}")
async def get_player_profile(riot_name: str, riot_tag: str, db: Session = Depends(get_db)):
    cached = find_riot_account(db, riot_name, riot_tag)
    puuid = cached["puuid"] if cached else None
    region = cached["region"] if cached else None

    account = await henrik_api.get_account_v2(riot_name, riot_tag)
    if account:
        puuid = account.get("puuid") or puuid
        region = account.get("region") or region
        upsert_riot_account(db, {
            "puuid": account.get("puuid"),
            "name": account.get("name", riot_name),
            "tag": account.get("tag", riot_tag),
            "region": account.get("region"),
        })
    elif not puuid:
        raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")

    region = region or _DEFAULT_REGION

    mmr = await henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag)
    matches = await henrik_api.get_matches(region, _PLATFORM, riot_name, riot_tag, size=20)

    return build_player_profile(
        db,
        riot_name=riot_name,
        riot_tag=riot_tag,
        puuid=puuid,
        account=account,
        mmr=mmr,
        matches_raw=matches if isinstance(matches, list) else [],
    )
