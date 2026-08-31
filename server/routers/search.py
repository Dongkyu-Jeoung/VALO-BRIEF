from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.connection import get_db
from services import henrik

router = APIRouter(prefix="/api/search", tags=["search"])


def _find_riot_account(db: Session, riot_name: str, riot_tag: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT puuid, riot_name, riot_tag
            FROM riot_accounts
            WHERE riot_name = :riot_name AND riot_tag = :riot_tag
            LIMIT 1
            """
        ),
        {"riot_name": riot_name, "riot_tag": riot_tag},
    ).mappings().first()
    return dict(row) if row else None


def _cache_riot_account(db: Session, account: dict) -> None:
    """Henrik 조회로 존재가 확인된 계정을 riot_accounts에 캐싱 (다음 검색부터는 DB로 응답)."""
    if not account.get("puuid") or not account.get("name") or not account.get("tag"):
        return

    db.execute(
        text(
            """
            INSERT INTO riot_accounts (puuid, riot_name, riot_tag, region, platform)
            VALUES (:puuid, :riot_name, :riot_tag, :region, 'pc')
            ON DUPLICATE KEY UPDATE
                riot_name = VALUES(riot_name),
                riot_tag = VALUES(riot_tag),
                region = VALUES(region)
            """
        ),
        {
            "puuid": account["puuid"],
            "riot_name": account["name"],
            "riot_tag": account["tag"],
            "region": account.get("region") or "kr",
        },
    )
    db.commit()


def _find_team(db: Session, team_name: str, team_tag: str) -> dict | None:
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
    cached = _find_riot_account(db, riot_name, riot_tag)
    if cached is not None:
        return {"exists": True, "riotId": cached["riot_name"], "tag": cached["riot_tag"]}

    account = await henrik.get_account(riot_name, riot_tag)
    if account is None:
        return {"exists": False, "riotId": riot_name, "tag": riot_tag}

    _cache_riot_account(db, account)
    return {"exists": True, "riotId": account.get("name", riot_name), "tag": account.get("tag", riot_tag)}


@router.get("/teams/{team_name}/{team_tag}/exists")
async def check_team_exists(team_name: str, team_tag: str, db: Session = Depends(get_db)):
    cached = _find_team(db, team_name, team_tag)
    if cached is not None:
        return {"exists": True, "teamName": cached["team_name"], "teamTag": cached["team_tag"]}

    team = await henrik.get_premier_team(team_name, team_tag)
    if team is None:
        return {"exists": False, "teamName": team_name, "teamTag": team_tag}

    # teams 테이블은 사이트 회원가입 계정(email/login_id/password_hash 필수)과 결합되어 있어
    # Henrik 조회만으로는 캐싱하지 않음 - 실제 가입 흐름에서만 row가 생성됨
    return {"exists": True, "teamName": team.get("name", team_name), "teamTag": team.get("tag", team_tag)}
