"""
team_engagement_cache의 trade_rate/duelist_acs/win 중 하나라도 NULL로 남아있는 과거
행을 Henrik 매치 상세로 다시 채우는 1회성 백필 스크립트(구 scripts/
backfill_engagement_win.py를 일반화 - win만이 아니라 trade_rate/duelist_acs NULL도
같이 잡는다).

NULL이 남는 이유는 컬럼마다 다르다:
  - win: 2026-09-12에 추가된 컬럼이라(마이그레이션 15번, database/valo_brief.sql) 그
    이전에 write-through된 행은 전부 NULL이었다.
  - trade_rate/duelist_acs: ml/engagement_predictor.py::trade_rate_from_matches/
    duelist_acs_from_matches가 "계산 불가"(로스터를 못 찾음, 킬 이벤트 없음, 듀얼리스트
    요원이 없음 등)일 때 의도적으로 None을 반환한다 - 이 스크립트를 돌려도 진짜 계산
    불가인 매치는 다시 None으로 남는 게 정상이다(그 매치는 실제로 그 값이 없는 것).
공통적으로, write-through는 "그 팀을 다시 조회"할 때만 다시 도는데 이미 지나간 매치는
다시 조회될 일이 없어 자연 치유가 안 된다 - 그래서 한 번은 직접 훑어줘야 한다.

services/match_history.py::upsert_match_history를 그대로 재사용하지 않는 이유: 그
함수는 matches/match_player_stats도 같이 갱신하고 match_player_stats.started_at을
"넘겨받은 값으로 무조건 덮어쓰는데"(started_at_raw 없이 부르면 None으로 덮어써서 기존
값을 지워버림) 여기서는 started_at_raw(프리미어 히스토리 API 값)를 따로 구할 이유가
없다 - team_engagement_cache 컬럼만 고치면 되므로, services/team_engagement_cache.py
::upsert_match_engagement만 직접 호출해 그 테이블만 건드린다(matches/match_player_stats는
전혀 손대지 않음).
"""
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from database.connection import SessionLocal
from ml import engagement_predictor
from services import henrik_api, team_engagement_cache
from services.henrik_api import HenrikRateLimitError

sys.stdout.reconfigure(encoding="utf-8")

# GENERAL 키 한도(43/분)는 검색/화면 등 실사용 트래픽과 공유된다(services/henrik_config.py) -
# 사용자가 개발 서버(--reload)를 별도로 띄워두고 화면도 같이 쓰는 중일 수 있어, 이 백필이
# 그 예산을 독차지하면 실제 화면 조회가 503(HenrikRateLimitError)을 맞을 수 있다. 그래서
# 동시 요청 수를 낮추고 배치 사이에 쉬는 시간을 둔다.
BATCH_SIZE = 3
BATCH_DELAY_SECONDS = 3.0


def _parse_game_start(value) -> datetime | None:
    """services/match_history.py::_parse_game_start와 동일 로직(private 함수 의존 대신
    이 스크립트에 그대로 복제 - 백필 전용이라 별도 모듈로 뺄 만큼은 아님)."""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
    return None


async def _fetch(match_id: str):
    try:
        return match_id, await henrik_api.get_match_detail(match_id)
    except HenrikRateLimitError:
        return match_id, "RATE_LIMITED"


def _apply_match(db, match_id: str, match: dict) -> int:
    """match 상세 하나에서 양쪽 팀의 trade_rate/duelist_acs/win을 재계산해
    team_engagement_cache에 upsert. 반환값: 갱신 시도한 행 수(0~2)."""
    teams = match.get("teams") or {}
    red = teams.get("red") or {}
    blue = teams.get("blue") or {}
    red_roster = red.get("roster") or {}
    blue_roster = blue.get("roster") or {}
    red_id = red_roster.get("id")
    blue_id = blue_roster.get("id")
    red_won = red.get("has_won")
    blue_won = blue.get("has_won")
    game_start = _parse_game_start((match.get("metadata") or {}).get("game_start"))

    updated = 0
    if red_id:
        team_engagement_cache.upsert_match_engagement(
            db, red_id, match_id,
            opponent_team_id=blue_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
            win=red_won if isinstance(red_won, bool) else None,
        )
        updated += 1
    if blue_id:
        team_engagement_cache.upsert_match_engagement(
            db, blue_id, match_id,
            opponent_team_id=red_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
            win=blue_won if isinstance(blue_won, bool) else None,
        )
        updated += 1
    return updated


async def backfill():
    db = SessionLocal()
    try:
        match_ids = [
            row[0] for row in db.execute(
                text(
                    "SELECT DISTINCT match_id FROM team_engagement_cache "
                    "WHERE win IS NULL OR trade_rate IS NULL OR duelist_acs IS NULL"
                )
            ).all()
        ]
    finally:
        db.close()

    print(f"백필 대상 매치 수: {len(match_ids)}")
    if not match_ids:
        return

    rows_updated = 0
    still_null: list[str] = []
    no_detail: list[str] = []
    rate_limited: list[str] = []

    for i in range(0, len(match_ids), BATCH_SIZE):
        batch = match_ids[i:i + BATCH_SIZE]
        fetched = await asyncio.gather(*(_fetch(mid) for mid in batch))

        db = SessionLocal()
        try:
            for match_id, match in fetched:
                if match == "RATE_LIMITED":
                    rate_limited.append(match_id)
                    continue
                if not match:
                    no_detail.append(match_id)
                    continue
                try:
                    rows_updated += _apply_match(db, match_id, match)
                except Exception as e:
                    db.rollback()
                    still_null.append(match_id)
                    print(f"  [실패] match_id={match_id}: {e}")
        finally:
            db.close()

        print(f"  진행: {min(i + BATCH_SIZE, len(match_ids))}/{len(match_ids)} "
              f"(누적 갱신 행 {rows_updated}건)")
        if i + BATCH_SIZE < len(match_ids):
            await asyncio.sleep(BATCH_DELAY_SECONDS)

    # 레이트리밋으로 건너뛴 것만 한 번 더, 훨씬 느린 속도로 재시도한다(이 시점엔 대부분
    # 지나갔을 확률이 높음 - 그래도 남으면 최종 목록만 보고하고 스크립트를 다시 돌리면 됨).
    if rate_limited:
        print(f"레이트리밋 {len(rate_limited)}건 재시도(1건씩, 간격 2초)...")
        retry_targets, rate_limited = rate_limited, []
        for match_id in retry_targets:
            match_id2, match = await _fetch(match_id)
            if match == "RATE_LIMITED":
                rate_limited.append(match_id)
            elif not match:
                no_detail.append(match_id)
            else:
                db = SessionLocal()
                try:
                    rows_updated += _apply_match(db, match_id, match)
                except Exception as e:
                    db.rollback()
                    still_null.append(match_id)
                    print(f"  [실패] match_id={match_id}: {e}")
                finally:
                    db.close()
            await asyncio.sleep(2.0)

    print(f"완료 - 갱신된 행: {rows_updated}건")
    if no_detail:
        print(f"매치 상세를 못 찾음(삭제/비공개 등 추정): {len(no_detail)}건")
    if rate_limited:
        print(f"레이트리밋으로 건너뜀(재실행 필요): {len(rate_limited)}건")
    if still_null:
        print(f"예외로 실패: {len(still_null)}건")


if __name__ == "__main__":
    asyncio.run(backfill())
