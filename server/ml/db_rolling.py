"""DB 최근 5경기를 모델 입력으로 변환한다."""
from datetime import datetime, timedelta, timezone
from math import isfinite

import pandas as pd
from sqlalchemy import text

from ml.rolling import RECENT_MATCHES, aggregate_player_rows

# game_start는 저장 서비스와 동일하게 KST naive datetime이다.
# 경기 경과 일수로 탈락시키지 않고 DB의 최신 5경기를 사용한다.
_KST = timezone(timedelta(hours=9))


def get_recent_agent(df):
    return df.iloc[0].get("agent", "Unknown") if len(df) else "Unknown"


def load_recent_matches(db, puuid):
    """유효성 필터를 LIMIT보다 먼저 적용한다. 요원은 통계 경기 선택과 독립적이다."""
    if db is None:
        return pd.DataFrame()
    now = datetime.now(_KST).replace(tzinfo=None)
    latest = db.execute(text("""
        SELECT a.display_name AS agent, s.agent_uuid
        FROM match_player_stats s
        JOIN matches m ON m.match_id = s.match_id
        LEFT JOIN ref_agents a ON a.uuid = s.agent_uuid
        WHERE s.puuid = :puuid AND m.game_start <= :now
          AND LOWER(COALESCE(m.mode, '')) NOT IN
              ('deathmatch', 'team deathmatch', 'escalation')
        ORDER BY m.game_start DESC, m.match_id DESC LIMIT 1
    """), {"puuid": puuid, "now": now}).mappings().first()
    query = text("""
        SELECT s.match_id, s.puuid, s.team_id, s.agent_uuid, s.role_type,
               a.display_name AS agent, s.acs, s.kills, s.deaths,
               s.kast, s.headshot_pct, m.game_start,
               m.team_a_id, m.team_b_id, m.rounds_won_a, m.rounds_won_b
        FROM match_player_stats AS s
        JOIN matches AS m ON s.match_id = m.match_id
        LEFT JOIN ref_agents AS a ON s.agent_uuid = a.uuid
        WHERE s.puuid = :puuid
          AND LOWER(COALESCE(m.mode, '')) NOT IN
              ('deathmatch', 'team deathmatch', 'escalation')
          AND m.game_start <= :now
          AND s.acs >= 0 AND s.kills >= 0 AND s.deaths >= 0
          AND s.kast BETWEEN 0 AND 100
          AND s.headshot_pct BETWEEN 0 AND 100
          AND m.rounds_won_a >= 0 AND m.rounds_won_b >= 0
          AND m.rounds_won_a + m.rounds_won_b > 0
          AND (
              (s.team_id = m.team_a_id AND (m.team_b_id IS NULL OR s.team_id <> m.team_b_id))
              OR (s.team_id = m.team_b_id AND (m.team_a_id IS NULL OR s.team_id <> m.team_a_id))
          )
        ORDER BY m.game_start DESC, m.match_id DESC
        LIMIT :limit
    """)
    df = pd.read_sql(query, db.connection(), params={"puuid": puuid, "limit": RECENT_MATCHES, "now": now})
    # 최신 경기의 지표가 결측이어도 요원은 그 경기의 값을 유지한다.
    if not df.empty:
        df["agent"] = latest["agent"] if latest else None
        df["agent_uuid"] = latest["agent_uuid"] if latest else None
    return df


def build_db_player_feature(df, report=None):
    """불완전한 이력은 None으로 반환하여 캐시/API로 보완한다."""
    def reject(reason):
        if report is not None:
            report(reason)
        return None

    if df is None or len(df) != RECENT_MATCHES:
        return reject(f"MATCH_COUNT: rows={0 if df is None else len(df)}, required={RECENT_MATCHES}")
    try:
        if df["match_id"].nunique() != RECENT_MATCHES:
            return reject(f"MATCH_ID_INVALID: unique={df['match_id'].nunique()}, required={RECENT_MATCHES}")
        dates = pd.to_datetime(df["game_start"], errors="coerce")
        now = datetime.now(_KST).replace(tzinfo=None)
        if dates.isna().any():
            return reject(f"DATE_MISSING: matches={df.loc[dates.isna(), 'match_id'].tolist()}")
        if (dates > now).any():
            return reject(f"DATE_FUTURE: latest={dates.max()}, now_kst={now}")
        rows = df.to_dict("records")
        agent = get_recent_agent(df)
        if not isinstance(agent, str) or not agent.strip() or agent == "Unknown":
            return reject(f"AGENT_MISSING: match={rows[0].get('match_id')}, agent_uuid={rows[0].get('agent_uuid')!r}")
        for row in rows:
            match_id = row.get("match_id")
            for col in ("acs", "kills", "deaths", "kast", "headshot_pct", "win"):
                try:
                    value = float(row[col])
                except (KeyError, TypeError, ValueError, OverflowError):
                    return reject(f"METRIC_INVALID: match={match_id}, column={col}, value={row.get(col)!r}")
                maximum = 1 if col == "win" else 100 if col in ("kast", "headshot_pct") else float("inf")
                if not isfinite(value) or not 0 <= value <= maximum:
                    return reject(f"METRIC_INVALID: match={match_id}, column={col}, value={value}")
            kills, deaths = float(row["kills"]), float(row["deaths"])
            if not all(isfinite(v) and v >= 0 for v in (kills, deaths)):
                return reject(f"KD_INVALID: match={match_id}, kills={kills}, deaths={deaths}")
            # API 추출기와 같은 경기별 KD 반올림.
            row["kd"] = round(kills / max(1, deaths), 2)
        return aggregate_player_rows(rows, rows[0]["puuid"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return reject(f"FEATURE_INVALID: {type(exc).__name__}: {exc}")


def add_match_side(df):
    df = df.copy()

    def calc_side(row):
        team = row["team_id"]
        if pd.isna(team):
            raise ValueError("선수 team_id가 없습니다.")
        is_a = pd.notna(row["team_a_id"]) and team == row["team_a_id"]
        is_b = pd.notna(row["team_b_id"]) and team == row["team_b_id"]
        if is_a == is_b:
            raise ValueError(f"경기 팀 식별 실패: {row['match_id']}")
        return "A" if is_a else "B"

    df["match_side"] = df.apply(calc_side, axis=1)
    return df


def add_win_column(df):
    df = df.copy()

    def calc_win(row):
        try:
            a, b = float(row["rounds_won_a"]), float(row["rounds_won_b"])
        except (TypeError, ValueError) as exc:
            raise ValueError("경기 점수가 없습니다.") from exc
        if not all(isfinite(v) and v >= 0 and v.is_integer() for v in (a, b)) or a + b == 0:
            raise ValueError("경기 점수가 유효하지 않습니다.")
        if row["match_side"] not in ("A", "B"):
            raise ValueError("경기 팀 구분이 유효하지 않습니다.")
        return int(a > b if row["match_side"] == "A" else b > a)

    df["win"] = df.apply(calc_win, axis=1)
    return df
