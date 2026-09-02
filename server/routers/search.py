"""
개인/팀 통합 검색 (SearchBox) - 존재 여부 확인 및 프로필 페이지 데이터 프리페치.
"""
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from database.connection import SessionLocal, get_db
from services import cosmetics, henrik_api
from services.riot_accounts import find_riot_account, upsert_riot_account

router = APIRouter(prefix="/api/search", tags=["search"])

# 이 앱은 KR 위주 서비스라, region을 모르는 최초 검색에서 kr로 추측해 mmr_history/matches를
# 계정 조회와 "진짜 동시에" 먼저 당겨본다. 맞으면 계정 조회 왕복 시간만큼 이득이고, 틀리면 그
# 추측 호출만 버려지고(레이트리밋만 조금 낭비) 확정 region으로 다시 당겨온다 - exists 응답이나
# 프로필 데이터의 정확성에는 영향 없음(틀린 값은 캐시/DB에 저장되지 않음).
_GUESS_REGION = "kr"

# FastAPI의 BackgroundTasks는 응답 전송 후에만 실행되는데, 그와 달리 요청 처리 중에 진짜
# 동시에 도는 fire-and-forget 태스크가 필요해서 별도로 관리한다. asyncio는 참조가 없는
# 태스크를 GC할 수 있어 완료 전까지는 이 set에 붙잡아둔다.
_inflight_prefetches: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> None:
    """응답을 기다리지 않고 백그라운드로 진짜 동시에 실행하는 태스크 등록."""
    task = asyncio.create_task(coro)
    _inflight_prefetches.add(task)
    task.add_done_callback(_inflight_prefetches.discard)


async def _prefetch_cosmetics(riot_name: str, riot_tag: str) -> None:
    """account.card/title을 미리 resolve해서 프로필 진입 시 ref_player_cards/titles 캐시가
    이미 데워져 있게 한다 (안 하면 mmr_history/matches는 프리페치로 이미 캐시됐는데 카드/칭호만
    valorant-api.com 왕복 시간(~0.7s)이 그대로 노출됨 - 실측으로 확인한 케이스).
    fire-and-forget이라 응답 전송 후에도 계속 돌 수 있어 요청 스코프 세션 대신 독립된
    세션을 새로 열고 직접 정리한다."""
    account = await henrik_api.get_account(riot_name, riot_tag)  # 캐시 히트면 즉시 반환
    if not account:
        return
    db = SessionLocal()
    try:
        await asyncio.gather(
            cosmetics.resolve_card(db, account.get("card")),
            cosmetics.resolve_title(db, account.get("title")),
        )
    finally:
        db.close()


def _prefetch_profile_data(region: str, riot_name: str, riot_tag: str) -> None:
    _fire_and_forget(henrik_api.get_account(riot_name, riot_tag))
    _fire_and_forget(henrik_api.get_mmr_history(region, riot_name, riot_tag))
    _fire_and_forget(henrik_api.get_stored_matches(region, riot_name, riot_tag))
    _fire_and_forget(_prefetch_cosmetics(riot_name, riot_tag))


def _find_team(db: Session, team_name: str, team_tag: str) -> dict | None:
    """teams 테이블에서 팀명#태그로 캐시된 row 조회."""
    row = db.execute(
        text(
            """
            SELECT team_id, team_name, team_tag
            FROM teams
            WHERE team_name = :team_name AND team_tag = :team_tag
            LIMIT 1
            """
        ),
        {"team_name": team_name, "team_tag": team_tag},
    ).mappings().first()
    return dict(row) if row else None


@router.get("/players/{riot_name}/{riot_tag}/exists")
async def check_player_exists(riot_name: str, riot_tag: str, db: Session = Depends(get_db)):
    """개인 검색 존재 확인. DB 캐시 우선 조회, 없으면 Henrik으로 검증 후 캐싱.
    존재가 확인되면 이어질 프로필 조회를 백그라운드로 프리페치한다."""
    cached = find_riot_account(db, riot_name, riot_tag)
    if cached is not None:
        _prefetch_profile_data(cached["region"], riot_name, riot_tag)
        return {"exists": True, "riotId": cached["riot_name"], "tag": cached["riot_tag"]}

    # region을 모르는 최초 검색 - 계정 조회 결과를 기다리는 동안 kr로 추측해 병행 프리페치
    _fire_and_forget(henrik_api.get_mmr_history(_GUESS_REGION, riot_name, riot_tag))
    _fire_and_forget(henrik_api.get_stored_matches(_GUESS_REGION, riot_name, riot_tag))

    account = await henrik_api.get_account(riot_name, riot_tag)
    if account is None:
        return {"exists": False, "riotId": riot_name, "tag": riot_tag}

    upsert_riot_account(db, account)
    region = account.get("region") or "kr"
    if region != _GUESS_REGION:
        # 추측이 틀렸으면 확정된 region으로 다시 프리페치 (틀린 추측은 그냥 버려짐)
        _prefetch_profile_data(region, riot_name, riot_tag)
    else:
        # region 추측은 맞아서 mmr_history/matches는 이미 프리페치 중이지만, 카드/칭호는
        # _prefetch_profile_data를 안 거쳤으니 따로 데워준다
        _fire_and_forget(_prefetch_cosmetics(riot_name, riot_tag))
    return {"exists": True, "riotId": account.get("name", riot_name), "tag": account.get("tag", riot_tag)}


@router.get("/teams/{team_name}/{team_tag}/exists")
async def check_team_exists(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    """팀 검색 존재 확인. DB 캐시 우선 조회, 없으면 Henrik 프리미어 팀 API로 검증."""
    cached = _find_team(db, team_name, team_tag)
    if cached is not None:
        return {"exists": True, "teamName": cached["team_name"], "teamTag": cached["team_tag"]}

    team = await henrik_api.get_premier_team(team_name, team_tag)
    if team is None:
        return {"exists": False, "teamName": team_name, "teamTag": team_tag}

    # teams 테이블은 사이트 회원가입 계정(email/login_id/password_hash 필수)과 결합되어 있어
    # Henrik 조회만으로는 캐싱하지 않음 - 실제 가입 흐름에서만 row가 생성됨
    return {"exists": True, "teamName": team.get("name", team_name), "teamTag": team.get("tag", team_tag)}
