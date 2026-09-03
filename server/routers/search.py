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
from services.team_profile import MATCH_HISTORY_LIMIT

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


async def _prefetch_cosmetics(account: dict) -> None:
    """account.card/title을 미리 resolve해서 프로필 진입 시 ref_player_cards/titles 캐시가
    이미 데워져 있게 한다 (안 하면 mmr_history/matches는 프리페치로 이미 캐시됐는데 카드/칭호만
    valorant-api.com 왕복 시간(~0.7s)이 그대로 노출됨 - 실측으로 확인한 케이스).
    account는 호출부가 이미 조회해둔 걸 그대로 받는다(get_account 중복 호출 방지).
    fire-and-forget이라 응답 전송 후에도 계속 돌 수 있어 요청 스코프 세션 대신 독립된
    세션을 새로 열고 직접 정리한다."""
    db = SessionLocal()
    try:
        await asyncio.gather(
            cosmetics.resolve_card(db, account.get("card")),
            cosmetics.resolve_title(db, account.get("title")),
        )
    finally:
        db.close()


async def _prefetch_account_and_cosmetics(riot_name: str, riot_tag: str) -> None:
    """account를 모를 때만 쓰는 경로 - 조회 1번으로 카드/칭호까지 이어서 처리."""
    account = await henrik_api.get_account(riot_name, riot_tag)
    if account:
        await _prefetch_cosmetics(account)


def _prefetch_profile_data(region: str, riot_name: str, riot_tag: str, account: dict | None = None) -> None:
    """account를 이미 갖고 있으면(존재확인에서 이미 조회한 경우) 다시 부르지 않고 그대로 쓴다
    - 예전엔 이 함수 안에서 get_account를 또 불러서 존재확인 때의 조회와 겹쳤었음."""
    if account:
        _fire_and_forget(_prefetch_cosmetics(account))
    else:
        _fire_and_forget(_prefetch_account_and_cosmetics(riot_name, riot_tag))
    _fire_and_forget(henrik_api.get_mmr_history(region, riot_name, riot_tag))
    _fire_and_forget(henrik_api.get_stored_matches(region, riot_name, riot_tag))


async def _prefetch_team_profile_data(team_name: str, team_tag: str) -> None:
    """팀 존재확인 이후 팀 프로필 진입에 대비해 이력+매치상세를 미리 캐시에 데워둔다
    (개인검색의 _prefetch_profile_data와 같은 목적/구조). team_info 자체는 exists 체크에서
    이미 get_premier_team()으로 호출/캐싱됐으므로 여기서는 history부터 이어서 당긴다."""
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    league_matches = (history or {}).get("league_matches") or []
    recent = sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)
    match_ids = [m["id"] for m in recent[:MATCH_HISTORY_LIMIT] if m.get("id")]
    if match_ids:
        await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids))


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
        # account는 방금 위에서 이미 조회했으니 그대로 넘겨서 다시 부르지 않는다
        _prefetch_profile_data(region, riot_name, riot_tag, account=account)
    else:
        # region 추측은 맞아서 mmr_history/matches는 이미 프리페치 중이지만, 카드/칭호는
        # _prefetch_profile_data를 안 거쳤으니 따로 데워준다(account 재조회 없이 바로 사용)
        _fire_and_forget(_prefetch_cosmetics(account))
    return {"exists": True, "riotId": account.get("name", riot_name), "tag": account.get("tag", riot_tag)}


@router.get("/teams/{team_name}/{team_tag}/exists")
async def check_team_exists(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    """팀 검색 존재 확인. DB 캐시 우선 조회, 없으면 Henrik 프리미어 팀 API로 검증.
    존재가 확인되면 이어질 팀 프로필 조회(이력+매치상세)를 개인검색과 동일하게 백그라운드로
    프리페치한다 - 안 하면 팀 프로필 진입 시 이력/매치상세 비용(~2.7~3.1초, 실측)을 그때
    처음부터 그대로 다 물어야 함."""
    cached = _find_team(db, team_name, team_tag)
    if cached is not None:
        _fire_and_forget(_prefetch_team_profile_data(team_name, team_tag))
        return {"exists": True, "teamName": cached["team_name"], "teamTag": cached["team_tag"]}

    team = await henrik_api.get_premier_team(team_name, team_tag)
    if team is None:
        return {"exists": False, "teamName": team_name, "teamTag": team_tag}

    _fire_and_forget(_prefetch_team_profile_data(team_name, team_tag))

    # teams 테이블은 사이트 회원가입 계정(email/login_id/password_hash 필수)과 결합되어 있어
    # Henrik 조회만으로는 캐싱하지 않음 - 실제 가입 흐름에서만 row가 생성됨
    return {"exists": True, "teamName": team.get("name", team_name), "teamTag": team.get("tag", team_tag)}
