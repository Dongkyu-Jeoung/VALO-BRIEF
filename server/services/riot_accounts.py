"""
riot_accounts 테이블 캐시 조회/저장. search.py, players.py 공용.
Henrik 조회로 존재가 확인된 계정을 캐싱해두면 다음 조회부터는 DB로 바로 응답할 수 있다.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

def find_riot_account(db: Session, riot_name: str, riot_tag: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT puuid, riot_name, riot_tag, region, platform,
                   account_level, title, current_rank, current_rr
            FROM riot_accounts
            WHERE riot_name = :riot_name AND riot_tag = :riot_tag
            LIMIT 1
            """
        ),
        {"riot_name": riot_name, "riot_tag": riot_tag},
    ).mappings().first()
    return dict(row) if row else None


def upsert_riot_account(db: Session, account: dict, mmr: dict | None = None) -> None:
    """account(Henrik account API 응답)와, 있다면 mmr(Henrik mmr API 응답)까지
    한 번에 캐싱한다. mmr을 안 넘기면(검색 존재확인 경로) 랭크 관련 컬럼은 기존 값을 유지한다."""
    if not account.get("puuid") or not account.get("name") or not account.get("tag"):
        return

    current = (mmr or {}).get("current") or {}
    current_rank = (current.get("tier") or {}).get("name")
    current_rr = current.get("rr")

    db.execute(
        text(
            """
            INSERT INTO riot_accounts
                (puuid, riot_name, riot_tag, region, platform, account_level, title, current_rank, current_rr)
            VALUES
                (:puuid, :riot_name, :riot_tag, :region, 'pc', :account_level, :title, :current_rank, :current_rr)
            ON DUPLICATE KEY UPDATE
                riot_name = VALUES(riot_name),
                riot_tag = VALUES(riot_tag),
                region = VALUES(region),
                account_level = COALESCE(VALUES(account_level), account_level),
                title = COALESCE(VALUES(title), title),
                current_rank = COALESCE(VALUES(current_rank), current_rank),
                current_rr = COALESCE(VALUES(current_rr), current_rr)
            """
        ),
        {
            "puuid": account["puuid"],
            "riot_name": account["name"],
            "riot_tag": account["tag"],
            "region": account.get("region") or "kr",
            "account_level": account.get("account_level"),
            "title": account.get("title"),
            "current_rank": current_rank,
            "current_rr": current_rr,
        },
    )
    db.commit()
