from ml.valorant_git import (
    get_puuid_by_riot_id,
    get_matches_v4,
    get_match_detail_v4,
    extract_player_rows_from_match
)

REGION = "kr"
PLATFORM = "pc"
RECENT_MATCHES = 5


def build_player_feature(name: str, tag: str):

    # 1. Riot ID -> PUUID
    puuid = get_puuid_by_riot_id(name, tag)

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