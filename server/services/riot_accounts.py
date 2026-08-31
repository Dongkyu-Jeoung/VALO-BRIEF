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
            SELECT puuid, riot_name, riot_tag, region, platform
            FROM riot_accounts
            WHERE riot_name = :riot_name AND riot_tag = :riot_tag
            LIMIT 1
            """
        ),
        {"riot_name": riot_name, "riot_tag": riot_tag},
    ).mappings().first()
    return dict(row) if row else None


def upsert_riot_account(db: Session, account: dict) -> None:
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
