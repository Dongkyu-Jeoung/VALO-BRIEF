from datetime import datetime, timedelta, timezone

from sqlalchemy import text

def resolve_recent_roster_from_db(db, team_id: str):
    """최신 경기만 읽는다. 불완전한 로스터는 호출부에서 API로 보완한다."""
    if db is None:
        return None, []
    query = text("""
        SELECT s.match_id, s.puuid, m.game_start
        FROM matches AS m
        JOIN match_player_stats AS s ON s.match_id = m.match_id
        WHERE m.match_id = (
            SELECT latest.match_id FROM matches AS latest
            WHERE latest.team_a_id = :team_id OR latest.team_b_id = :team_id
            ORDER BY latest.game_start DESC, latest.match_id DESC
            LIMIT 1
        ) AND s.team_id = :team_id
        ORDER BY s.puuid
    """)
    rows = db.execute(query, {"team_id": team_id}).mappings().all()
    if not rows:
        return None, []
    info = {"match_id": rows[0]["match_id"]}
    started = rows[0]["game_start"]
    now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    if started is None or started > now:
        return info, []
    roster = [{"puuid": puuid} for puuid in dict.fromkeys(row["puuid"] for row in rows) if puuid]
    return info, roster if len(roster) == 5 else []
