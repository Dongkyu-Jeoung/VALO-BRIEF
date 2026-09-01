import asyncio

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

    # account 조회는 v1/v2 두 번 부르지 않고 henrik_api.get_account() 한 번으로 통일
    # (puuid/region/account_level/title 모두 포함)
    if region:
        # region을 이미 알고 있으면(검색 exists 체크가 직전에 캐싱해둔 것이 보통) account
        # 응답을 기다릴 필요가 없다 - mmr/matches를 곧바로 같이 호출한다.
        # 실사용 흐름(검색 -> 프로필 진입)에서는 거의 항상 이 경로를 탄다 (실측 2.79s -> 1.93s)
        account, mmr, matches = await asyncio.gather(
            henrik_api.get_account(riot_name, riot_tag),
            henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag),
            henrik_api.get_matches(region, _PLATFORM, riot_name, riot_tag, size=20),
        )
    else:
        # region을 전혀 모르는 순수 최초 조회 - mmr/matches를 부르려면 account 응답의
        # region이 필요해서 건너뛸 수 없는 순차 의존성이다. 존재 자체가 불확실하므로
        # account가 실패하면 mmr/matches를 헛되이 부르지 않고 바로 404 처리한다.
        account = await henrik_api.get_account(riot_name, riot_tag)
        if not account:
            raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")
        region = account.get("region") or _DEFAULT_REGION
        mmr, matches = await asyncio.gather(
            henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag),
            henrik_api.get_matches(region, _PLATFORM, riot_name, riot_tag, size=20),
        )

    if account:
        puuid = account.get("puuid") or puuid
        region = account.get("region") or region
    elif cached:
        # Henrik 호출이 실패(레이트리밋/일시 장애 등)해도 캐시가 있으면 마지막으로
        # 확인된 레벨/칭호로 프로필을 계속 보여준다
        account = {
            "puuid": cached.get("puuid"),
            "name": cached.get("riot_name"),
            "tag": cached.get("riot_tag"),
            "account_level": cached.get("account_level"),
            "title": cached.get("title"),
            "region": cached.get("region"),
        }
    else:
        raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")

    if account.get("puuid"):
        # account_level/title과 mmr의 current_rank/current_rr을 한 번에 캐싱
        upsert_riot_account(db, account, mmr)

    return build_player_profile(
        db,
        riot_name=riot_name,
        riot_tag=riot_tag,
        puuid=puuid,
        account=account,
        mmr=mmr,
        matches_raw=matches if isinstance(matches, list) else [],
    )
