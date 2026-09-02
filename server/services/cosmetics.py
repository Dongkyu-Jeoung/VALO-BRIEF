"""
플레이어 카드(아바타)/칭호 uuid를 사람이 보는 값으로 변환. Henrik account API가 주는
card/title은 uuid라 그대로 노출하면 안 되고, ref_player_cards/ref_player_titles에
DB 캐시가 있으면 그대로 쓰고 없으면 valorant-api.com에서 한 번 조회해 캐싱한다.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from services import valorant_api


async def resolve_card(db: Session, uuid: str | None) -> str | None:
    """카드 uuid -> 아바타 이미지 URL(display_icon)."""
    if not uuid:
        return None

    row = db.execute(
        text("SELECT display_icon FROM ref_player_cards WHERE uuid = :uuid"),
        {"uuid": uuid},
    ).mappings().first()
    if row:
        return row["display_icon"]

    card = await valorant_api.get_player_card(uuid)
    if not card:
        return None

    display_icon = card.get("displayIcon")
    db.execute(
        text(
            """
            INSERT INTO ref_player_cards (uuid, name_ko, display_icon)
            VALUES (:uuid, :name_ko, :display_icon)
            ON DUPLICATE KEY UPDATE name_ko = VALUES(name_ko), display_icon = VALUES(display_icon)
            """
        ),
        {"uuid": uuid, "name_ko": card.get("displayName"), "display_icon": display_icon},
    )
    db.commit()
    return display_icon


async def resolve_title(db: Session, uuid: str | None) -> str | None:
    """칭호 uuid -> 한글 텍스트."""
    if not uuid:
        return None

    row = db.execute(
        text("SELECT title_ko FROM ref_player_titles WHERE uuid = :uuid"),
        {"uuid": uuid},
    ).mappings().first()
    if row:
        return row["title_ko"]

    title = await valorant_api.get_player_title(uuid)
    if not title:
        return None

    title_ko = title.get("titleText") or title.get("displayName")
    db.execute(
        text(
            """
            INSERT INTO ref_player_titles (uuid, title_ko)
            VALUES (:uuid, :title_ko)
            ON DUPLICATE KEY UPDATE title_ko = VALUES(title_ko)
            """
        ),
        {"uuid": uuid, "title_ko": title_ko},
    )
    db.commit()
    return title_ko
