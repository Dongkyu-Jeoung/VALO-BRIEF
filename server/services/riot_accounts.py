"""
riot_accounts 테이블 캐시 조회/저장. search.py, players.py 공용.
Henrik 조회로 존재가 확인된 계정을 캐싱해두면 다음 조회부터는 DB로 바로 응답할 수 있다.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

# updated_at을 DB의 DEFAULT/ON UPDATE CURRENT_TIMESTAMP에 맡기면 RDS 서버 타임존(보통 UTC)
# 기준으로 저장돼 한국 시간보다 9시간 느리게 찍힌다. DB 서버 타임존 설정을 건드리는 대신,
# 애플리케이션에서 KST로 직접 계산해 매번 명시적으로 넣어준다(DATETIME 컬럼이라 타임존 정보
# 없이 벽시계 값만 저장되므로, KST로 계산한 값을 그대로 넣으면 DB 설정과 무관하게 항상 맞음).
_KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def find_riot_account(db: Session, riot_name: str, riot_tag: str) -> dict | None:
    """riot_name#riot_tag로 캐시된 계정 row를 조회. 없으면 None."""
    row = db.execute(
        text(
            """
            SELECT puuid, riot_name, riot_tag, region, platform,
                   account_level, title, avatar_url, current_rank, current_rr
            FROM riot_accounts
            WHERE riot_name = :riot_name AND riot_tag = :riot_tag
            LIMIT 1
            """
        ),
        {"riot_name": riot_name, "riot_tag": riot_tag},
    ).mappings().first()
    return dict(row) if row else None


def upsert_riot_account(
    db: Session,
    account: dict,
    mmr_history: dict | None = None,
    *,
    title: str | None = None,
    avatar_url: str | None = None,
) -> None:
    """account(Henrik account API 응답)와, 있다면 mmr_history(Henrik v2/mmr 응답)의
    current_data까지 한 번에 캐싱한다. title/avatar_url은 cosmetics.resolve_*로 이미 변환된
    값을 명시적으로 넘길 때만 갱신한다 - account.get("title")은 uuid라 여기서 직접 쓰면 안 된다.
    아무것도 안 넘기면(검색 존재확인 경로) 해당 컬럼들은 기존 값을 그대로 유지한다."""
    if not account.get("puuid") or not account.get("name") or not account.get("tag"):
        return

    current_data = (mmr_history or {}).get("current_data") or {}
    current_rank = current_data.get("currenttierpatched")
    current_rr = current_data.get("ranking_in_tier")

    db.execute(
        text(
            """
            INSERT INTO riot_accounts
                (puuid, riot_name, riot_tag, region, platform, account_level, title, avatar_url, current_rank, current_rr, updated_at)
            VALUES
                (:puuid, :riot_name, :riot_tag, :region, 'pc', :account_level, :title, :avatar_url, :current_rank, :current_rr, :updated_at)
            ON DUPLICATE KEY UPDATE
                riot_name = VALUES(riot_name),
                riot_tag = VALUES(riot_tag),
                region = VALUES(region),
                account_level = COALESCE(VALUES(account_level), account_level),
                title = COALESCE(VALUES(title), title),
                avatar_url = COALESCE(VALUES(avatar_url), avatar_url),
                current_rank = COALESCE(VALUES(current_rank), current_rank),
                current_rr = COALESCE(VALUES(current_rr), current_rr),
                updated_at = VALUES(updated_at)
            """
        ),
        {
            "puuid": account["puuid"],
            "riot_name": account["name"],
            "riot_tag": account["tag"],
            "region": account.get("region") or "kr",
            "account_level": account.get("account_level"),
            "title": title,
            "avatar_url": avatar_url,
            "current_rank": current_rank,
            "current_rr": current_rr,
            "updated_at": _now_kst(),
        },
    )
    db.commit()
