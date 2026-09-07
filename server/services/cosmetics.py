"""
플레이어 카드(아바타)/칭호 uuid를 사람이 보는 값으로 변환. Henrik account API가 주는
card/title은 uuid라 그대로 노출하면 안 되고, ref_player_cards/ref_player_titles에
DB 캐시가 있으면 그대로 쓰고 없으면 valorant-api.com에서 한 번 조회해 캐싱한다.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.cosmetics import RefPlayerCard, RefPlayerTitle
from services import valorant_api


async def resolve_card(db: Session, uuid: str | None) -> str | None:
    """카드 uuid -> 아바타 이미지 URL(display_icon)."""
    if not uuid:
        return None

    cached = db.get(RefPlayerCard, uuid)
    if cached is not None:
        return cached.display_icon

    card = await valorant_api.get_player_card(uuid)
    if not card:
        return None

    display_icon = card.get("displayIcon")
    db.add(RefPlayerCard(uuid=uuid, name_ko=card.get("displayName"), display_icon=display_icon))
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청이 먼저 캐싱한 경우 - 그 값을 그대로 쓴다
        db.rollback()
        existing = db.get(RefPlayerCard, uuid)
        return existing.display_icon if existing else display_icon
    return display_icon


async def resolve_title(db: Session, uuid: str | None) -> str | None:
    """칭호 uuid -> 한글 텍스트."""
    if not uuid:
        return None

    cached = db.get(RefPlayerTitle, uuid)
    if cached is not None:
        return cached.title_ko

    title = await valorant_api.get_player_title(uuid)
    if not title:
        return None

    title_ko = title.get("titleText") or title.get("displayName")
    db.add(RefPlayerTitle(uuid=uuid, title_ko=title_ko))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(RefPlayerTitle, uuid)
        return existing.title_ko if existing else title_ko
    return title_ko
