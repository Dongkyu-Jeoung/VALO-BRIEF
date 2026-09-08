"""
player_rolling_cache 테이블 캐시 조회/저장. ml/rolling.py 공용(build_player_feature가
Henrik에서 새로 계산한 Rolling Feature를 캐싱하고, 다음 예측 때 재사용).

캐시는 puuid 단위로 "최근 N경기 평균" 값 자체를 저장한다 - 선수가 새 경기를 하면 값이
바뀌므로 riot_accounts(계정 정보, 사실상 무기한 유효)와 달리 TTL을 둬서 일정 시간이
지나면 무효로 취급한다. TTL 안에서는 Henrik 요청 없이 그대로 재사용한다.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.player_rolling_cache import PlayerRollingCache

# riot_accounts.py와 동일한 이유(DB DEFAULT/ON UPDATE CURRENT_TIMESTAMP는 RDS 서버
# 타임존 기준이라 KST보다 9시간 느리게 찍힘) - 애플리케이션에서 KST로 직접 계산해 넣는다.
_KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def find_fresh_player_feature(db: Session, puuid: str, ttl: timedelta) -> dict | None:
    """캐시가 있고 ttl 이내면 build_player_feature와 동일한 형태의 dict를 반환, 아니면 None."""
    row = db.get(PlayerRollingCache, puuid)
    if row is None:
        return None
    if row.computed_at is None or _now_kst() - row.computed_at > ttl:
        return None

    return {
        "puuid": row.puuid,
        "agent": row.agent,
        "recent_acs": row.recent_acs,
        "recent_kd": row.recent_kd,
        "recent_kast": row.recent_kast,
        "recent_headshot_pct": row.recent_headshot_pct,
        "recent_winrate": row.recent_winrate,
    }


def upsert_player_feature(db: Session, feature: dict) -> PlayerRollingCache:
    """build_player_feature()가 새로 계산한 feature dict 하나를 캐시에 저장(갱신)한다."""
    row = db.get(PlayerRollingCache, feature["puuid"])
    if row is None:
        row = PlayerRollingCache(puuid=feature["puuid"])
        db.add(row)

    row.agent = feature["agent"]
    row.recent_acs = feature["recent_acs"]
    row.recent_kd = feature["recent_kd"]
    row.recent_kast = feature["recent_kast"]
    row.recent_headshot_pct = feature["recent_headshot_pct"]
    row.recent_winrate = feature["recent_winrate"]
    row.computed_at = _now_kst()

    db.commit()
    db.refresh(row)
    return row
