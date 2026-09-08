"""
로그인한 팀 전용 "우리팀 분석 > 통계" 탭 데이터 조립.

상대팀 검색(services/team_profile.py)과 다르게 Henrik을 실시간으로 부르지 않는다 - 이미
회원가입 시 services/match_sync.py가 matches/match_player_stats에 채워둔 캐시를 그대로
읽어서 응답한다 (로그인한 내 팀 데이터라 이미 DB에 있다는 전제).

레코드 필드 이름/의미는 services/team_profile.py의 build_team_profile 출력과 최대한
맞췄다 - front StatsTab/ProfileHeader/TeamMatchRow가 TeamProfilePage와 공용 컴포넌트라
같은 모양이어야 한다.
"""
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, defer

from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team import Team
from services.player_profile import _load_ref_agents

# matchHistory에 담을 최대 매치 수. Henrik 실시간 호출 비용이 없는 DB 캐시 조회라
# services/team_profile.py의 MATCH_HISTORY_LIMIT(10, 매치당 ~1.3MB 실시간 호출 비용
# 때문에 작게 잡힌 값)보다 넉넉하게 잡았다.
MATCH_HISTORY_LIMIT = 50

# RecentSummaryBox 라벨("최근 20게임 전적")과 맞춘 집계 대상 게임 수.
RECENT_SUMMARY_LIMIT = 20

_map_name_cache: dict | None = None


def _load_map_name_by_uuid(db: Session) -> dict:
    """ref_maps.uuid(소문자) -> 한글 표시명. matches.map_uuid로 조인하기 위함."""
    global _map_name_cache
    if _map_name_cache is not None:
        return _map_name_cache
    rows = db.execute(text("SELECT uuid, name_ko, display_name FROM ref_maps")).mappings().all()
    _map_name_cache = {r["uuid"].lower(): (r["name_ko"] or r["display_name"]) for r in rows}
    return _map_name_cache


def _season_act_for(dt: datetime) -> tuple[str, str]:
    """연도당 6개 Act(2개월씩)로 나누는 달력 기반 추정 (services/team_profile.py와 동일 규칙 -
    v2/match에는 player_profile.py가 쓰는 진짜 Episode/Act 코드가 없어서 팀 쪽은 이 근사치를 쓴다)."""
    season = f"S{dt.year}"
    act_index = (dt.month - 1) // 2
    return season, f"Act {act_index + 1}"


def _format_datetime(dt: datetime | None) -> tuple[str, str]:
    if dt is None:
        return "-", "-"
    return dt.strftime("%m.%d"), dt.strftime("%I:%M %p").lstrip("0")


def build_my_team_stats(db: Session, team: Team) -> dict:
    team_id = team.team_id

    # team_a_id/team_b_id에 대한 OR + ORDER BY를 한 쿼리로 묶으면 MySQL이 인덱스를 못 타고
    # round_detail_json(라운드 원본 JSON, 매치당 용량이 큼)까지 통째로 정렬 버퍼에 올려서
    # "Out of sort memory"가 났다(실측 확인). 이 응답엔 round_detail_json이 필요 없으니
    # defer()로 SELECT 대상에서 빼고, team_a_id/team_b_id 쿼리를 각각 자기 인덱스로 따로
    # 돌린 뒤 애플리케이션에서 합쳐 정렬한다 - 팀 하나가 가진 매치 수는 많아야 수백 건이라
    # 파이썬에서 합쳐 정렬해도 비용이 미미하다.
    base_query = db.query(Match).options(defer(Match.round_detail_json))
    matches_by_id = {
        m.match_id: m
        for m in (
            base_query.filter(Match.team_a_id == team_id).all()
            + base_query.filter(Match.team_b_id == team_id).all()
        )
    }
    matches = sorted(
        matches_by_id.values(),
        key=lambda m: m.game_start or datetime.min,
        reverse=True,
    )[:MATCH_HISTORY_LIMIT]

    match_ids = [m.match_id for m in matches]
    stats_rows = (
        db.query(MatchPlayerStat)
        .filter(MatchPlayerStat.match_id.in_(match_ids), MatchPlayerStat.team_id == team_id)
        .all()
        if match_ids
        else []
    )

    puuids = {s.puuid for s in stats_rows}
    riot_names = (
        {r.puuid: r.riot_name for r in db.query(RiotAccount).filter(RiotAccount.puuid.in_(puuids)).all()}
        if puuids
        else {}
    )

    agents = _load_ref_agents(db)
    map_names = _load_map_name_by_uuid(db)

    by_match: dict[str, list[MatchPlayerStat]] = {}
    for s in stats_rows:
        by_match.setdefault(s.match_id, []).append(s)

    match_history = []
    map_buckets: dict[str, dict] = {}

    for match in matches:
        roster = by_match.get(match.match_id) or []
        if not roster:
            continue  # 우리 로스터 스탯이 비어있는 매치(수집 당시 일부만 저장된 경우) - 방어적으로 제외

        is_team_a = match.team_a_id == team_id
        our_rounds = (match.rounds_won_a if is_team_a else match.rounds_won_b) or 0
        opp_rounds = (match.rounds_won_b if is_team_a else match.rounds_won_a) or 0
        result = "win" if match.winner_team_id == team_id else "lose"

        kills = sum(s.kills or 0 for s in roster)
        deaths = sum(s.deaths or 0 for s in roster)
        assists = sum(s.assists or 0 for s in roster)
        kda = round((kills + assists) / deaths, 2) if deaths else float(kills + assists)

        adr_values = [s.adr for s in roster if s.adr is not None]
        acs_values = [s.acs for s in roster if s.acs is not None]
        adr = round(sum(adr_values) / len(adr_values)) if adr_values else None
        acs = round(sum(acs_values) / len(acs_values)) if acs_values else None
        first_blood = sum(s.first_bloods or 0 for s in roster)

        mvp_player = max(roster, key=lambda s: s.acs or 0)
        mvp_agent = agents["by_uuid"].get((mvp_player.agent_uuid or "").lower()) or {}
        mvp_deaths = mvp_player.deaths or 0
        mvp_kda_num = (mvp_player.kills or 0) + (mvp_player.assists or 0)
        mvp_kda = round(mvp_kda_num / mvp_deaths, 2) if mvp_deaths else float(mvp_kda_num)

        map_name = map_names.get((match.map_uuid or "").lower(), "-")
        date_str, time_str = _format_datetime(match.game_start)
        season, act = _season_act_for(match.game_start) if match.game_start else ("-", "-")

        match_history.append({
            "map": map_name,
            "result": result,
            "date": date_str,
            "time": time_str,
            "roundScore": f"{our_rounds}-{opp_rounds}",
            "roundsWon": our_rounds,
            "roundsLost": opp_rounds,
            "kda": kda,
            "adr": adr,
            "acs": acs,
            "firstBlood": first_blood,
            "mvp": {
                "agent": mvp_agent.get("name_ko") or "-",
                "player": riot_names.get(mvp_player.puuid, "-"),
                "kda": mvp_kda,
                "hs": round(mvp_player.headshot_pct) if mvp_player.headshot_pct is not None else 0,
                "acs": mvp_player.acs or 0,
            },
            "season": season,
            "act": act,
        })

        bucket = map_buckets.setdefault(map_name, {"map": map_name, "win": 0, "lose": 0})
        bucket["win" if result == "win" else "lose"] += 1

    map_winrates = [
        {**b, "winRate": round(b["win"] / (b["win"] + b["lose"]) * 100)}
        for b in map_buckets.values()
        if (b["win"] + b["lose"]) > 0
    ]

    by_puuid: dict[str, list[MatchPlayerStat]] = {}
    for s in stats_rows:
        by_puuid.setdefault(s.puuid, []).append(s)

    ranking = []
    for puuid, rows in by_puuid.items():
        acs_values = [r.acs for r in rows if r.acs is not None]
        hs_values = [r.headshot_pct for r in rows if r.headshot_pct is not None]
        kills = sum(r.kills or 0 for r in rows)
        deaths = sum(r.deaths or 0 for r in rows)
        role_type = next((r.role_type for r in rows if r.role_type), "-")
        ranking.append({
            "name": riot_names.get(puuid, "-"),
            "acs": round(sum(acs_values) / len(acs_values)) if acs_values else 0,
            "hs": round(sum(hs_values) / len(hs_values)) if hs_values else 0,
            "position": role_type,
            "kd": round(kills / deaths, 2) if deaths else float(kills),
        })
    ranking.sort(key=lambda p: p["acs"], reverse=True)
    player_ranking = ranking[:5]
    for i, p in enumerate(player_ranking, start=1):
        p["rank"] = i

    recent = matches[:RECENT_SUMMARY_LIMIT]
    recent_wins = sum(1 for m in recent if m.winner_team_id == team_id)
    recent_our_rounds = [(m.rounds_won_a if m.team_a_id == team_id else m.rounds_won_b) or 0 for m in recent]
    recent_opp_rounds = [(m.rounds_won_b if m.team_a_id == team_id else m.rounds_won_a) or 0 for m in recent]
    recent_summary = {
        "winRate": round(recent_wins / len(recent) * 100) if recent else 0,
        "wins": recent_wins,
        "losses": len(recent) - recent_wins,
        "avgRoundWin": round(sum(recent_our_rounds) / len(recent), 1) if recent else 0,
        "avgRoundLose": round(sum(recent_opp_rounds) / len(recent), 1) if recent else 0,
    }

    return {
        "name": team.team_name,
        "tag": team.team_tag,
        "division": f"디비전 {team.division}" if team.division else None,
        "ratingIconUrl": team.team_image,
        "recentSummary": recent_summary,
        "playerRanking": player_ranking,
        "mapWinrates": map_winrates,
        "matchHistory": match_history,
    }
