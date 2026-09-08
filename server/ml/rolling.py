from datetime import timedelta

from sqlalchemy.orm import Session

from ml.valorant_git import (
    get_puuid_by_riot_id,
    get_matches_v4,
    get_match_detail_v4,
    extract_player_rows_from_match
)
from services.player_rolling_cache import find_fresh_player_feature, upsert_player_feature
from services.riot_accounts import find_riot_account

REGION = "kr"
PLATFORM = "pc"
RECENT_MATCHES = 5

# Rolling Feature(선수 최근 N경기 평균) 캐시 유효 시간. 경쟁전 한 판 평균 소요시간보다
# 넉넉하게 잡아, 캐시 적중 시 Henrik 요청(선수당 puuid 1 + matches 1 + match detail
# RECENT_MATCHES건 = 최대 6건)을 완전히 건너뛴다 - 승부예측_성능_분석.md 5번 참고.
ROLLING_CACHE_TTL = timedelta(minutes=20)


def resolve_puuid(name: str, tag: str, db: Session | None = None) -> str | None:
    """Riot ID -> PUUID (캐시 재사용). 검색/프로필 조회 등에서 이미 riot_accounts에
    캐싱된 선수라면 Henrik(v2/account) 호출 없이 그 puuid를 바로 쓴다. db가 없거나 캐시에
    없는 선수라면 Henrik에 직접 물어본다 - 승부예측_성능_분석.md 5-1번 참고.

    build_player_feature와 별도 함수로 뺀 이유(5-4번): predict_blue_win이 선수 10명을
    ThreadPoolExecutor로 병렬 처리하는데, SQLAlchemy Session은 스레드-세이프하지 않다 -
    그래서 db를 쓰는 이 단계는 병렬 구간 진입 "전"에 순차로 다 끝내고, puuid가 정해진
    뒤부터(=이 함수 이후)만 병렬로 돌린다."""
    cached = find_riot_account(db, name, tag) if db is not None else None
    return cached.puuid if cached is not None else get_puuid_by_riot_id(name, tag)


def get_cached_player_feature(db: Session | None, puuid: str) -> dict | None:
    """player_rolling_cache에서 puuid의 Rolling Feature를 조회. ROLLING_CACHE_TTL
    이내로 신선하면 build_player_feature와 동일한 형태의 dict를, 없거나 오래됐으면
    None을 반환한다(호출부가 None이면 build_player_feature로 새로 계산).

    resolve_puuid와 같은 이유로 build_player_feature 밖으로 뺐다: predict_blue_win이
    puuid 10개를 ThreadPoolExecutor로 병렬 처리하기 "전"에, db를 쓰는 캐시 조회를
    순차로 다 끝내야 한다(SQLAlchemy Session은 스레드-세이프하지 않음)."""
    if db is None:
        return None

    return find_fresh_player_feature(db, puuid, ROLLING_CACHE_TTL)


def save_player_feature_cache(db: Session | None, feature: dict) -> None:
    """build_player_feature가 Henrik에서 새로 계산한 feature 하나를 캐시에 저장.
    get_cached_player_feature와 마찬가지로 병렬 구간이 끝난 뒤 순차로만 호출한다."""
    if db is None:
        return

    upsert_player_feature(db, feature)


def build_player_feature(name: str, tag: str, db: Session | None = None, puuid: str | None = None):

    # 1. Riot ID -> PUUID - puuid가 이미 주어졌으면(predict_blue_win이 병렬 구간 진입
    # 전에 미리 resolve해둔 경우) 그대로 쓰고, 없으면 이 함수 안에서 직접 resolve한다
    # (routers/predict.py의 저수준 테스트 엔드포인트, ml/test_predict.py 등 db 없이
    # 단독으로 호출하는 경로용).
    if puuid is None:
        puuid = resolve_puuid(name, tag, db)

    if puuid is None:
        raise ValueError(f"{name}#{tag} PUUID 조회 실패")

    # 2. 최근 5경기
    matches = get_matches_v4(
        REGION,
        PLATFORM,
        puuid,
        RECENT_MATCHES
    )

    rows = []

    for m in matches:

        match_id = m["metadata"]["match_id"]

        detail = get_match_detail_v4(
            REGION,
            match_id
        )

        if detail is None:
            continue

        player_rows = extract_player_rows_from_match(
            detail,
            puuid
        )

        if len(player_rows):
            rows.append(player_rows[0])

    if len(rows) == 0:
        raise ValueError(f"{name} 최근 경기 없음")

    # 평균 계산
    acs = sum(r["acs"] for r in rows) / len(rows)
    kd = sum(r["kd"] for r in rows) / len(rows)
    kast = sum(r["kast"] for r in rows) / len(rows)
    hs = sum(r["headshot_pct"] for r in rows) / len(rows)
    winrate = sum(r["win"] for r in rows) / len(rows)

    return {
        "puuid": puuid,
        "agent": rows[0]["agent"],
        "recent_acs": round(acs, 2),
        "recent_kd": round(kd, 2),
        "recent_kast": round(kast, 2),
        "recent_headshot_pct": round(hs, 2),
        "recent_winrate": round(winrate, 2)
    }