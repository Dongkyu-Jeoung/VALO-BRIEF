# DB 기반 Rolling Feature

import pandas as pd

# DB 매치 정보 load -> 최근 5경기 조회
def load_recent_matches(conn, puuid):

    query = """
        SELECT
            puuid,
            started_at,
            role_type,
            acs,
            kills,
            deaths,
            kast,
            headshot_pct
        FROM match_stats
        WHERE puuid = %s
        ORDER BY started_at DESC
        LIMIT 5
    """

    df = pd.read_sql(query, conn, params=[puuid])

    return df

# Rolling Feature 생성
# DB는 이미 최근 5경기만 가져오기 때문에 평균만 계산하면 됩니다.
# 여기서 recent_winrate만 아직 계산되지 않습니다.
def build_db_player_feature(df):

    if len(df) == 0:
        return None

    return {
        "recent_acs": df["acs"].mean(),
        "recent_kd": (
            df["kills"].sum() /
            max(1, df["deaths"].sum())
        ),
        "recent_kast": df["kast"].mean(),
        "recent_headshot_pct": df["headshot_pct"].mean(),
        "recent_winrate": None,          # 다음 단계
        "is_duelist": int(
            (df["role_type"] == "Duelist").sum() >= 3
        )
    }

# Winrate 계산
# DB에 team_id와 match_id가 있으므로 승패를 구할 수 있습니다.
# DB 에 승패 정보가 저장 되어 있어야 함 !
def calculate_winrate(df):

    wins = (
        df["team_result"] == "Win"
    ).sum()

    return round(
        wins / len(df) * 100,
        1
    )