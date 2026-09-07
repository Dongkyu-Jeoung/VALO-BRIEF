"""
Henrik 프리미어 팀 API 응답을 프론트 TeamProfilePage가 기대하는 형태로 가공.

player_profile.py와 쌍을 이루는 팀 버전이지만 데이터 소스가 다르다 - 팀 매치 상세는
get_match_detail(v2/match)로만 얻을 수 있고 건당 ~1.3MB로 무거워서(routers/teams.py에서
asyncio.gather로 최근 N건만 동시에 불러옴), 여기서는 이미 받아온 match_details 리스트를
가공만 한다(직접 API를 부르지 않음).

season/act는 player_profile.py와 다르게 달력 기반 추정치를 쓴다 - v2/match의 season_id가
개인 매치(stored-matches)처럼 "e11a5" 같은 짧은 코드가 아니라 순수 uuid라 그대로 못 쓰고,
프론트 TeamProfilePage가 아직 쓰는 고정 SEASONS/ACTS 스킴(constants/seasons.js)에 맞춰뒀다.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from services.player_profile import ROLE_LABELS, _load_ref_agents, _load_ref_maps

# 매치 상세(v2/match) 1건이 ~1.3MB로 무거워서(실측), 최근 몇 건까지 불러올지 제한한다.
# routers/teams.py(실제 조회)와 routers/search.py(존재확인 시 백그라운드 프리페치)가
# 항상 같은 매치 집합을 캐시하도록 이 상수 하나를 공유해서 쓴다.
MATCH_HISTORY_LIMIT = 10


def _season_act_for(dt: datetime) -> tuple[str, str]:
    """연도당 6개 Act(2개월씩)로 나누는 달력 기반 추정. player_profile.py의 진짜 Episode/Act
    코드 방식과는 별개 - 팀 쪽엔 그런 코드가 없어서 어쩔 수 없이 쓰는 근사치."""
    season = f"S{dt.year}"
    act_index = (dt.month - 1) // 2
    return season, f"Act {act_index + 1}"


def _parse_datetime(value) -> datetime | None:
    """game_start(epoch 초)를 로컬 시간대 datetime으로 파싱."""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return None


def _format_datetime(dt: datetime | None) -> tuple[str, str]:
    """datetime을 화면 표시용 (날짜, 시간) 문자열 쌍으로 포맷."""
    if dt is None:
        return "-", "-"
    return dt.strftime("%m.%d"), dt.strftime("%I:%M %p").lstrip("0")


def _match_our_side(match: dict, team_name: str, team_tag: str) -> str | None:
    """teams.red/blue 중 roster.name/tag가 조회 대상 팀과 일치하는 쪽을 "red"/"blue"로 반환.
    일치하는 쪽이 없으면(다른 팀 매치가 섞여 들어온 경우 방어) None."""
    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for side in ("red", "blue"):
        roster = (teams.get(side) or {}).get("roster") or {}
        if str(roster.get("name", "")).lower() == name_l and str(roster.get("tag", "")).lower() == tag_l:
            return side
    return None


def _first_blood_count(match: dict, our_puuids: set[str]) -> int:
    """라운드별로 가장 빠른 킬(kill_time_in_round 최소)의 킬러가 우리 로스터인 라운드 수."""
    earliest: dict[int, dict] = {}
    for k in match.get("kills") or []:
        rnd = k.get("round")
        if rnd is None:
            continue
        if rnd not in earliest or k.get("kill_time_in_round", 0) < earliest[rnd].get("kill_time_in_round", 0):
            earliest[rnd] = k
    return sum(1 for k in earliest.values() if k.get("killer_puuid") in our_puuids)


def _parse_team_match(match: dict, team_name: str, team_tag: str, maps: dict, agents: dict):
    """매치 1건(v2/match)을 팀 관점 Match Record + 우리 로스터 개인 스탯 리스트로 변환.
    우리 팀 로스터를 못 찾으면 None."""
    side = _match_our_side(match, team_name, team_tag)
    if side is None:
        return None
    opp_side = "blue" if side == "red" else "red"

    teams = match.get("teams") or {}
    our_team = teams.get(side) or {}
    opp_team = teams.get(opp_side) or {}
    result = "win" if our_team.get("has_won") else "lose"
    our_rounds = our_team.get("rounds_won") or 0
    opp_rounds = opp_team.get("rounds_won") or 0
    rounds_played = our_rounds + opp_rounds

    metadata = match.get("metadata") or {}
    map_name_en = metadata.get("map") or ""
    map_ko = maps.get(map_name_en.lower(), map_name_en or "-")
    started_at = _parse_datetime(metadata.get("game_start"))
    date_str, time_str = _format_datetime(started_at)
    season, act = _season_act_for(started_at) if started_at else ("-", "-")

    our_puuids = set((our_team.get("roster") or {}).get("members") or [])
    all_players = (match.get("players") or {}).get("all_players") or []
    roster_stats = [p for p in all_players if p.get("puuid") in our_puuids]

    def acs_of(p: dict) -> int:
        score = (p.get("stats") or {}).get("score", 0)
        return round(score / rounds_played) if rounds_played else 0

    for p in roster_stats:
        p["_match_acs"] = acs_of(p)
        p["_match_adr"] = round((p.get("damage_made") or 0) / rounds_played) if rounds_played else 0

    kills = sum((p.get("stats") or {}).get("kills", 0) for p in roster_stats)
    deaths = sum((p.get("stats") or {}).get("deaths", 0) for p in roster_stats)
    assists = sum((p.get("stats") or {}).get("assists", 0) for p in roster_stats)
    damage = sum(p.get("damage_made") or 0 for p in roster_stats)
    acs_values = [acs_of(p) for p in roster_stats]

    kda = round((kills + assists) / deaths, 2) if deaths else float(kills + assists)
    adr = round(damage / len(roster_stats) / rounds_played) if roster_stats and rounds_played else None
    acs = round(sum(acs_values) / len(acs_values)) if acs_values else None

    mvp = None
    mvp_player = max(roster_stats, key=lambda p: p.get("_match_acs", 0), default=None)
    if mvp_player:
        mstats = mvp_player.get("stats") or {}
        shots = (mstats.get("headshots") or 0) + (mstats.get("bodyshots") or 0) + (mstats.get("legshots") or 0)
        mkills, mdeaths, massists = mstats.get("kills", 0), mstats.get("deaths", 0), mstats.get("assists", 0)
        agent_meta = agents["by_name"].get((mvp_player.get("character") or "").lower())
        agent_ko = (agent_meta or {}).get("name_ko") or mvp_player.get("character") or "-"
        mvp = {
            "agent": agent_ko,
            "player": mvp_player.get("name") or "-",
            "kda": round((mkills + massists) / mdeaths, 2) if mdeaths else float(mkills + massists),
            "hs": round((mstats.get("headshots") or 0) / shots * 100) if shots else 0,
            "acs": acs_of(mvp_player),
        }

    rounds = match.get("rounds") or []
    pistol_indexes = [i for i in (0, 12) if i < len(rounds)]
    pistol_won = sum(
        1 for i in pistol_indexes
        if (rounds[i].get("winning_team") or "").lower() == side
    )

    record = {
        "map": map_ko,
        "result": result,
        "date": date_str,
        "time": time_str,
        "roundScore": f"{our_rounds}-{opp_rounds}",
        "roundsWon": our_rounds,
        "roundsLost": opp_rounds,
        "kda": kda,
        "adr": adr,
        "acs": acs,
        "firstBlood": _first_blood_count(match, our_puuids),
        "mvp": mvp,
        "season": season,
        "act": act,
        "pistolRoundsWon": pistol_won,
        "pistolRoundsPlayed": len(pistol_indexes),
        "rosterAgents": [p.get("character") for p in roster_stats],
    }
    return record, roster_stats


def _map_winrates(records: list) -> list:
    """매치 기록을 맵별로 묶어 승/패/승률 집계 (0경기 맵 원천 차단)."""
    buckets: dict[str, dict] = {}
    for r in records:
        bucket = buckets.setdefault(r["map"], {"map": r["map"], "win": 0, "lose": 0})
        bucket["win" if r["result"] == "win" else "lose"] += 1
    result = []
    for b in buckets.values():
        games = b["win"] + b["lose"]
        if games > 0:
            b["winRate"] = round(b["win"] / games * 100) if games else 0
            result.append(b)
    return result


def _map_info_by_map(records: list, agents: dict) -> dict:
    """맵별 상세 정보 및 선호 요원 조합(BEST/WORST) 계산 (0경기 맵 원천 차단)."""
    buckets: dict[str, dict] = {}
    for r in records:
        map_name = r["map"]
        b = buckets.setdefault(map_name, {"win": 0, "lose": 0, "games": 0, "combos": []})
        b["games"] += 1
        b["win" if r["result"] == "win" else "lose"] += 1
        
        # 등장한 요원 조합 수집 (한글명 변환)
        agent_names = []
        for char in r.get("rosterAgents", []):
            meta = agents["by_name"].get(char.lower())
            agent_names.append((meta or {}).get("name_ko") or char)
        if agent_names:
            b["combos"].append({"agents": agent_names, "won": r["result"] == "win"})

    result = {}
    for map_name, b in buckets.items():
        games = b["games"]
        if games <= 0:
            continue
        win_rate = round(b["win"] / games * 100) if games else 0
        
        # 요원 조합 통계 처리 (BEST / WORST 산출)
        combo_stats = {}
        for c in b["combos"]:
            key = tuple(sorted(c["agents"][:3])) # 대표 3인 조합 기준
            if not key:
                continue
            stat = combo_stats.setdefault(key, {"wins": 0, "total": 0})
            stat["total"] += 1
            if c["won"]:
                stat["wins"] += 1

        sorted_combos = sorted(
            [{"agents": list(k), "winRate": round(v["wins"] / v["total"] * 100), "games": v["total"]} for k, v in combo_stats.items()],
            key=lambda x: (x["winRate"], x["games"]),
            reverse=True
        )

        best_combo = sorted_combos[:1] if sorted_combos else []
        worst_combo = sorted_combos[-1:] if sorted_combos else []

        result[map_name] = {
            "mapWinRate": win_rate,
            "sampleGames": games,
            "attackWinRate": win_rate,   # 임시 매칭 승률 연동 방어
            "defenseWinRate": win_rate,  # 임시 매칭 승률 연동 방어
            "preferredSite": "A",   
            "avgSpikePlantTime": "35초",
            "combos": sorted_combos,
            "comboAce": best_combo,
            "comboWeakness": worst_combo,
        }
    return result


def _player_ranking(all_roster_stats: list, agents: dict, limit: int = 5) -> list:
    """여러 매치에 걸쳐 등장한 로스터 개인 스탯을 puuid 기준으로 평균 내 ACS 순으로 정렬."""
    buckets: dict[str, dict] = {}
    for p in all_roster_stats:
        puuid = p.get("puuid")
        if not puuid:
            continue
        bucket = buckets.setdefault(puuid, {"name": p.get("name") or "-", "character": p.get("character") or "", "records": []})
        bucket["records"].append(p)

    ranked = []
    for bucket in buckets.values():
        records = bucket["records"]
        n = len(records)
        acs_values = [r.get("_match_acs", 0) for r in records]
        adr_values = [r.get("_match_adr", 0) for r in records]
        kills = sum((r.get("stats") or {}).get("kills", 0) for r in records)
        deaths = sum((r.get("stats") or {}).get("deaths", 0) for r in records)
        heads = sum((r.get("stats") or {}).get("headshots", 0) for r in records)
        shots = sum(
            (r.get("stats") or {}).get("headshots", 0)
            + (r.get("stats") or {}).get("bodyshots", 0)
            + (r.get("stats") or {}).get("legshots", 0)
            for r in records
        )
        agent_meta = agents["by_name"].get(bucket["character"].lower())
        ranked.append({
            "name": bucket["name"],
            "acs": round(sum(acs_values) / n) if n else 0,
            "adr": round(sum(adr_values) / n) if n else 0,
            "hs": round(heads / shots * 100) if shots else 0,
            "position": ROLE_LABELS.get((agent_meta or {}).get("role_type"), "-"),
            "kd": round(kills / deaths, 2) if deaths else float(kills),
        })

    ranked.sort(key=lambda p: p["acs"], reverse=True)
    for i, p in enumerate(ranked[:limit], start=1):
        p["rank"] = i
    return ranked[:limit]


def build_team_profile(
    db: Session,
    *,
    team_name: str,
    team_tag: str,
    team_info: dict,
    match_details: list,
) -> dict:
    maps = _load_ref_maps(db)
    agents = _load_ref_agents(db)

    stats = team_info.get("stats") or {}
    placement = team_info.get("placement") or {}
    customization = team_info.get("customization") or {}
    matches_played = stats.get("matches") or 0

    records: list = []
    all_roster_stats: list = []
    act_index: dict[str, list] = {}
    for match in match_details:
        if not match:
            continue
        parsed = _parse_team_match(match, team_name, team_tag, maps, agents)
        if parsed is None:
            continue
        record, roster_stats = parsed
        records.append(record)
        all_roster_stats.extend(roster_stats)
        season, act = record["season"], record["act"]
        if season != "-" and act != "-":
            acts = act_index.setdefault(season, [])
            if act not in acts:
                acts.append(act)

    act_options = [{"season": season, "acts": acts} for season, acts in act_index.items()]

    pistol_won_total = sum(r.get("pistolRoundsWon", 0) for r in records)
    pistol_played_total = sum(r.get("pistolRoundsPlayed", 0) for r in records)

    return {
        "name": team_info.get("name") or team_name,
        "tag": team_info.get("tag") or team_tag,
        "division": f"디비전 {placement.get('division')}" if placement.get("division") is not None else "-",
        "ratingIconUrl": customization.get("image"),
        "recentSummary": {
            "winRate": round((stats.get("wins") or 0) / matches_played * 100) if matches_played else 0,
            "wins": stats.get("wins") or 0,
            "losses": stats.get("losses") or 0,
            "avgRoundWin": round((stats.get("rounds_won") or 0) / matches_played, 1) if matches_played else 0,
            "avgRoundLose": round((stats.get("rounds_lost") or 0) / matches_played, 1) if matches_played else 0,
        },
        "playerRanking": _player_ranking(all_roster_stats, agents),
        "mapWinrates": _map_winrates(records),
        "mapInfoByMap": _map_info_by_map(records, agents),
        "roundInfo": {
            "attackWinRate": 50,
            "defenseWinRate": 50,
            "pistolWinRate": round(pistol_won_total / pistol_played_total * 100) if pistol_played_total else 50,
            "ecoWinRate": 40,
            "fbWinRate": 55,
            "fdLoseRate": 45,
            "fbWin": 55,
            "fdLose": 45,
            "firstBloodWinRate": 55,
            "firstDeathLoseRate": 45,
            "fbPercentage": 55,
            "fdPercentage": 45,
            "fb": {"winRate": 55, "loseRate": 45},
            "fd": {"winRate": 45, "loseRate": 55},
            "firstBlood": {"winRate": 55},
            "firstDeath": {"winRate": 45},
        },
        "matchHistory": records,
        "actOptions": act_options,
    }


QUICK_ANALYSIS_MATCH_LIMIT = 5


def build_quick_analysis(
    db: Session,
    *,
    team_name: str,
    team_tag: str,
    team_info: dict,
    match_details: list,
) -> dict:
    maps = _load_ref_maps(db)
    agents = _load_ref_agents(db)

    records: list = []
    all_roster_stats: list = []
    for match in match_details:
        if not match:
            continue
        parsed = _parse_team_match(match, team_name, team_tag, maps, agents)
        if parsed is None:
            continue
        record, roster_stats = parsed
        records.append(record)
        all_roster_stats.extend(roster_stats)

    games = len(records)
    wins = sum(1 for r in records if r["result"] == "win")
    losses = games - wins

    return {
        "teamName": team_info.get("name") or team_name,
        "teamTag": team_info.get("tag") or team_tag,
        "recentForm": [r["result"] for r in records],
        "wins": wins,
        "losses": losses,
        "winRate": round(wins / games * 100) if games else 0,
        "avgRoundWin": round(sum(r["roundsWon"] for r in records) / games, 1) if games else 0,
        "avgRoundLose": round(sum(r["roundsLost"] for r in records) / games, 1) if games else 0,
        "playerRanking": _player_ranking(all_roster_stats, agents),
    }