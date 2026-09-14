"""Persist compact engagement statistics without storing raw matches or player rows."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ml import engagement_predictor
from models.team import Team
from services import team_engagement_cache

_KST = timezone(timedelta(hours=9))


def _parse_game_start(value) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(_KST).replace(tzinfo=None)
    return None


def _parse_started_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(_KST).replace(tzinfo=None)


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(
            func.lower(Team.team_name) == team_name.strip().lower(),
            func.lower(Team.team_tag) == team_tag.strip().lower(),
        )
        .first()
    )
    return row[0] if row else None


def upsert_match_engagement_summary(
    db: Session, match_id: str, match: dict, started_at_raw: str | None = None,
) -> int:
    """Save at most two compact rows, keyed by Premier team ID and match ID."""
    if not match_id or not team_engagement_cache.ENGAGEMENT_CACHE_ENABLED:
        return 0
    metadata = match.get("metadata") or {}
    teams = match.get("teams") or {}
    rosters = {side: (teams.get(side) or {}).get("roster") or {} for side in ("red", "blue")}
    team_ids = {
        side: roster.get("id") or _find_team_id(db, roster.get("name"), roster.get("tag"))
        for side, roster in rosters.items()
    }
    game_start = _parse_game_start(metadata.get("game_start")) or _parse_started_at(started_at_raw)
    saved = 0
    for side, opponent in (("red", "blue"), ("blue", "red")):
        if not team_ids[side]:
            continue
        roster = rosters[side]
        won = (teams.get(side) or {}).get("has_won")
        team_engagement_cache.upsert_match_engagement(
            db, team_ids[side], match_id,
            opponent_team_id=team_ids[opponent],
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], roster.get("name", ""), roster.get("tag", ""),
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], roster.get("name", ""), roster.get("tag", ""),
            ),
            win=won if isinstance(won, bool) else None,
        )
        saved += 1
    return saved
