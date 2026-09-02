"""
개인 프로필 페이지(Frame 04) - 전체 프로필 조회, Act별 모드 스탯 조회.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from services import cosmetics, henrik_api
from services.riot_accounts import find_riot_account, upsert_riot_account
from services.player_profile import build_player_profile, build_mode_stats

router = APIRouter(prefix="/api/players", tags=["players"])

_DEFAULT_REGION = "kr"


async def _fetch_matches(region: str, riot_name: str, riot_tag: str) -> list:
    """size/mode를 안 주면 Henrik이 저장해둔 매치를 전부 반환한다(모드별 필터로 나눠 부를
    필요 없음 - 공식 문서 및 실측으로 확인: mode=competitive 단독 호출이 무필터 호출에
    이미 포함된 것과 완전히 동일한 결과를 준다)."""
    return await henrik_api.get_stored_matches(region, riot_name, riot_tag) or []


@router.get("/{riot_name}/{riot_tag}")
async def get_player_profile(riot_name: str, riot_tag: str, db: Session = Depends(get_db)):
    """개인 프로필 전체 조회. region이 이미 캐시돼 있으면(검색 직후 진입하는 일반적인 흐름)
    account/mmr_history/matches를 전부 동시에 호출하고, 모르면 계정 조회로 region을
    먼저 확정한 뒤 나머지를 호출한다."""
    cached = find_riot_account(db, riot_name, riot_tag)
    region = cached["region"] if cached else None

    if region:
        account_task = asyncio.create_task(henrik_api.get_account(riot_name, riot_tag))
        mmr_history_task = asyncio.create_task(henrik_api.get_mmr_history(region, riot_name, riot_tag))
        matches_task = asyncio.create_task(_fetch_matches(region, riot_name, riot_tag))
        account = await account_task
    else:
        # 존재 자체가 불확실하므로, 계정 조회가 실패하면 나머지를 헛되이 부르지 않고 바로 404
        account = await henrik_api.get_account(riot_name, riot_tag)
        if not account:
            raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")
        region = account.get("region") or _DEFAULT_REGION
        mmr_history_task = asyncio.create_task(henrik_api.get_mmr_history(region, riot_name, riot_tag))
        matches_task = asyncio.create_task(_fetch_matches(region, riot_name, riot_tag))

    # account가 준비되는 즉시(mmr_history/matches를 기다리지 않고) 카드/칭호 해석을 같이
    # 시작한다 - account.card/title만 있으면 되고 mmr_history/matches와는 무관한 작업이라,
    # gather로 다 같이 기다렸다가 시작하면 그만큼 순차 대기가 생겨서 불필요하다.
    cosmetics_task = None
    if account:
        region = account.get("region") or region
        cosmetics_task = asyncio.gather(
            cosmetics.resolve_card(db, account.get("card")),
            cosmetics.resolve_title(db, account.get("title")),
        )

    mmr_history, matches = await asyncio.gather(mmr_history_task, matches_task)

    if account:
        # card/title은 uuid라 그대로 못 씀 - ref_player_cards/titles 캐시(없으면
        # valorant-api.com에서 최초 1회 조회 후 캐싱)를 거쳐 한글 텍스트/아바타 URL로 변환
        avatar_url, title_ko = await cosmetics_task
        account = {**account, "title": title_ko, "avatarUrl": avatar_url}
    elif cached:
        # Henrik 호출이 실패(레이트리밋/일시 장애 등)해도 캐시가 있으면 마지막으로
        # 확인된 레벨/칭호/아바타로 프로필을 계속 보여준다
        account = {
            "puuid": cached.get("puuid"),
            "name": cached.get("riot_name"),
            "tag": cached.get("riot_tag"),
            "account_level": cached.get("account_level"),
            "title": cached.get("title"),
            "avatarUrl": cached.get("avatar_url"),
            "region": cached.get("region"),
        }
    else:
        raise HTTPException(status_code=404, detail="선수를 찾을 수 없습니다.")

    if account.get("puuid"):
        upsert_riot_account(db, account, mmr_history, title=account.get("title"), avatar_url=account.get("avatarUrl"))

    return build_player_profile(
        db,
        riot_name=riot_name,
        riot_tag=riot_tag,
        account=account,
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

    mmr_history, matches = await asyncio.gather(
        henrik_api.get_mmr_history(region, riot_name, riot_tag),
        _fetch_matches(region, riot_name, riot_tag),
    )

    return build_mode_stats(
        db,
        matches_raw=matches,
        mmr_history=mmr_history,
        season=season,
        act=act,
    )
