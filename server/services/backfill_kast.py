"""python -m services.backfill_kast --team-id TEAM_ID [--limit 20] [--apply]

기본 실행은 대상 ID만 조회한다. --apply는 경기별 API 원본을 검증하여 NULL KAST만 채운다.
round_detail_json은 최상위 kills/players 집계를 보존하지 않으므로 그것만으로 복원하지 않는다.
"""
import argparse
import asyncio

from sqlalchemy import update

from database.connection import SessionLocal
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from services import henrik_api
from services.match_sync import calculate_match_kast


async def backfill(team_id: str, limit: int, apply: bool = False):
    with SessionLocal() as db:
        candidates = (
            db.query(Match.match_id)
            .filter(db.query(MatchPlayerStat.match_id).filter(
                MatchPlayerStat.match_id == Match.match_id,
                MatchPlayerStat.team_id == team_id,
                MatchPlayerStat.kast.is_(None),
            ).exists())
            .order_by(Match.game_start.desc(), Match.match_id.desc())
            .limit(limit).all()
        )
    ids = [row[0] for row in candidates]
    print(f"KAST backfill: candidates={len(ids)}, apply={apply}", flush=True)
    changed = 0
    for match_id in ids:
        if not apply:
            print(f"[DRY RUN] {match_id}", flush=True)
            continue
        # DB 세션/트랜잭션을 열어둔 채 API 제한을 기다리지 않는다.
        match = await henrik_api.get_match_detail(match_id)
        if not match or (match.get("metadata") or {}).get("matchid") != match_id:
            print(f"[SKIP] {match_id}: missing/mismatched API match", flush=True)
            continue
        values = calculate_match_kast(match)
        if not values:
            print(f"[SKIP] {match_id}: incomplete/inconsistent round events", flush=True)
            continue
        updated = 0
        with SessionLocal() as db:
            for puuid, kast in values.items():
                result = db.execute(update(MatchPlayerStat).where(
                    MatchPlayerStat.match_id == match_id,
                    MatchPlayerStat.puuid == puuid,
                    MatchPlayerStat.kast.is_(None),
                ).values(kast=kast))
                updated += result.rowcount
            db.commit()
        changed += updated
        print(f"[UPDATED] {match_id}: rows={updated}", flush=True)
    print(f"KAST backfill complete: updated_rows={changed}", flush=True)
    return changed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    try:
        await backfill(args.team_id, args.limit, args.apply)
    finally:
        await henrik_api.aclose_client()


if __name__ == "__main__":
    asyncio.run(main())
