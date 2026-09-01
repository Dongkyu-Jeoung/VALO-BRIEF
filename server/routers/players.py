"""
개인 프로필 페이지(Frame 04) - 전체 프로필 조회, Act별 모드 스탯 조회.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from services import henrik_api
from services.riot_accounts import find_riot_account, upsert_riot_account
from services.player_profile import build_player_profile, build_mode_stats

router = APIRouter(prefix="/api/players", tags=["players"])

_DEFAULT_REGION = "kr"
_PLATFORM = "pc"


async def _fetch_matches(region: str, riot_name: str, riot_tag: str) -> list:
    """stored-matches(전체 모드 혼합)와 stored-matches(mode=competitive)를 병렬로 불러 합친다.
    무필터 조회는 플레이 빈도가 낮은 모드(대개 경쟁전)를 결과에서 밀어낼 수 있어서,
    competitive를 별도로 한 번 더 불러 빠진 경기를 보충한다. match id로 중복 제거."""
    general, competitive = await asyncio.gather(
        henrik_api.get_stored_matches(region, riot_name, riot_tag),
        henrik_api.get_stored_matches(region, riot_name, riot_tag, mode="competitive"),
    )
    seen: set[str] = set()
    merged: list = []
    for batch in (general or [], competitive or []):
        for m in batch:
            match_id = (m.get("meta") or {}).get("id")
            if match_id:
                if match_id in seen:
                    continue
                seen.add(match_id)
            merged.append(m)
    return merged


@router.get("/{riot_name}/{riot_tag}")
async def get_player_profile(riot_name: str, riot_tag: str, db: Session = Depends(get_db)):
    """개인 프로필 전체 조회. region이 이미 캐시돼 있으면(검색 직후 진입하는 일반적인 흐름)
    account/mmr/mmr_history/matches를 전부 동시에 호출하고, 모르면 계정 조회로 region을
    먼저 확정한 뒤 나머지를 호출한다."""
    cached = find_riot_account(db, riot_name, riot_tag)
    puuid = cached["puuid"] if cached else None
    region = cached["region"] if cached else None

    if region:
        account, mmr, mmr_history, matches = await asyncio.gather(
            henrik_api.get_account(riot_name, riot_tag),
            henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag),
            henrik_api.get_mmr_history(region, riot_name, riot_tag),
            _fetch_matches(region, riot_name, riot_tag),
        )
    else:
        # 존재 자체가 불확실하므로, 계정 조회가 실패하면 나머지를 헛되이 부르지 않고 바로 404
        account = await henrik_api.get_account(riot_name, riot_tag)
        if not account:
            raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")
        region = account.get("region") or _DEFAULT_REGION
        mmr, mmr_history, matches = await asyncio.gather(
            henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag),
            henrik_api.get_mmr_history(region, riot_name, riot_tag),
            _fetch_matches(region, riot_name, riot_tag),
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
        upsert_riot_account(db, account, mmr)

    return build_player_profile(
        db,
        riot_name=riot_name,
        riot_tag=riot_tag,
        account=account,
        mmr=mmr,
        mmr_history=mmr_history,
        matches_raw=matches,
    )


@router.get("/{riot_name}/{riot_tag}/mode-stats")
async def get_player_mode_stats(
    riot_name: str,
    riot_tag: str,
    season: str | None = None,
    act: str | None = None,
    db: Session = Depends(get_db),
):
    """ProfileHeader에서 사용자가 다른 Act를 선택했을 때 호출. 기본 선택 Act의 스탯은
    /api/players/{riot_name}/{riot_tag}가 이미 내려주므로 여기서 다시 부를 필요 없다.
    season/act는 actOptions 값 그대로(예: "Episode 11"/"Act 5")."""
    cached = find_riot_account(db, riot_name, riot_tag)
    region = cached["region"] if cached else None

    if not region:
        account = await henrik_api.get_account(riot_name, riot_tag)
        if not account:
            raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")
        region = account.get("region") or _DEFAULT_REGION
        upsert_riot_account(db, account)
    elif not cached.get("puuid"):
        raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")

    mmr, mmr_history, matches = await asyncio.gather(
        henrik_api.get_mmr(region, _PLATFORM, riot_name, riot_tag),
        henrik_api.get_mmr_history(region, riot_name, riot_tag),
        _fetch_matches(region, riot_name, riot_tag),
    )

    return build_mode_stats(
        db,
        matches_raw=matches,
        mmr=mmr,
        mmr_history=mmr_history,
        season=season,
        act=act,
    )
