"""
Henrik API 원본 응답(계정/MMR/매치리스트)을 프론트 PlayerProfilePage가
기대하는 형태(front/src/mocks/player.mock.js 참고)로 가공.

매치 파싱은 Henrik v4/matches 스키마를 기준으로 하되, 필드 존재를 보장할 수 없으므로
전부 방어적으로 .get()하고 매치 1건 파싱 실패는 전체 응답을 깨뜨리지 않도록 스킵한다.
"""

from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

MODE_LABELS = {
    "competitive": "경쟁전",
    "unrated": "일반",
    "swiftplay": "신속 플레이",
    "deathmatch": "데스매치",
    "spikerush": "스파이크 러시",
    "premier": "프리미어",
}

ROLE_LABELS = {
    "Duelist": "타격대",
    "Initiator": "척후대",
    "Sentinel": "감시자",
    "Controller": "전략가",
}

TIER_LABELS = {
    "iron": "아이언",
    "bronze": "브론즈",
    "silver": "실버",
    "gold": "골드",
    "platinum": "플래티넘",
    "diamond": "다이아몬드",
    "ascendant": "초월자",
    "immortal": "불멸",
    "radiant": "레디언트",
}

# Henrik 매치 응답에는 시즌/Act 라벨이 없어, 프론트 기본 필터값(SEASONS[0]/ACTS[0])으로 채운다.
# 실제 시즌 매핑이 필요해지면 이 두 상수만 교체하면 된다.
SEASON_PLACEHOLDER = "S2026"
ACT_PLACEHOLDER = "Act 1"

# 영문 티어 명칭의 한국어 변환
def _translate_rank(tier_patched: str | None) -> str | None:
    if not tier_patched:
        return None
    parts = tier_patched.split()
    base_ko = TIER_LABELS.get(parts[0].lower(), parts[0])
    rest = " ".join(parts[1:])
    return f"{base_ko} {rest}".strip()

# DB 참조 요원 데이터 조회 및 캐싱
def _load_ref_agents(db: Session) -> dict:
    rows = db.execute(text("SELECT uuid, display_name, name_ko, role_type FROM ref_agents")).mappings().all()
    by_uuid, by_name = {}, {}
    for r in rows:
        entry = {"name_ko": r["name_ko"] or r["display_name"], "role_type": r["role_type"]}
        by_uuid[r["uuid"].lower()] = entry
        by_name[r["display_name"].lower()] = entry
    return {"by_uuid": by_uuid, "by_name": by_name}

# DB 참조 맵 데이터 조회
def _load_ref_maps(db: Session) -> dict:
    rows = db.execute(text("SELECT display_name, name_ko FROM ref_maps")).mappings().all()
    return {r["display_name"].lower(): (r["name_ko"] or r["display_name"]) for r in rows}

# 매치 데이터 내 플레이어 리스트 방어적 추출
def _match_players(match: dict) -> list:
    players = match.get("players")
    if players is None:
        return []
    if isinstance(players, dict):
        return players.get("all_players") or []
    return players

# 전체 플레이어 중 검색 대상 유저 추출
def _find_me(players: list, puuid: str, riot_name: str, riot_tag: str) -> dict | None:
    for p in players:
        if p.get("puuid") == puuid:
            return p
    name_l, tag_l = riot_name.lower(), riot_tag.lower()
    for p in players:
        if str(p.get("name", "")).lower() == name_l and str(p.get("tag", "")).lower() == tag_l:
            return p
    return None

# 소속 팀의 승/패 라운드 수 산출
def _team_rounds(match: dict, team_id) -> tuple[int, int] | None:
    teams = match.get("teams")
    if isinstance(teams, list):
        mine = next((t for t in teams if t.get("team_id") == team_id), None)
        if mine is None:
            return None
        rounds = mine.get("rounds") or {}
        won, lost = rounds.get("won"), rounds.get("lost")
        return (won, lost) if won is not None and lost is not None else None
    if isinstance(teams, dict) and team_id:
        mine = teams.get(str(team_id).lower())
        if not isinstance(mine, dict):
            return None
        won, lost = mine.get("rounds_won"), mine.get("rounds_lost")
        return (won, lost) if won is not None and lost is not None else None
    return None

# 매치 최종 승패 및 스코어 문자열 판정
def _match_result(match: dict, team_id, rounds: tuple[int, int] | None) -> tuple[str, str]:
    teams = match.get("teams")
    won = None
    if isinstance(teams, list):
        mine = next((t for t in teams if t.get("team_id") == team_id), None)
        if mine is not None and "won" in mine:
            won = bool(mine["won"])
    elif isinstance(teams, dict) and team_id:
        mine = teams.get(str(team_id).lower())
        if isinstance(mine, dict) and "has_won" in mine:
            won = bool(mine["has_won"])

    if rounds:
        my_rounds, opp_rounds = rounds
        round_score = f"{my_rounds}-{opp_rounds}"
        if won is None:
            won = my_rounds > opp_rounds
    else:
        round_score = "-"
        won = bool(won)

    return ("win" if won else "lose"), round_score

# 한국시간대에 날짜 및 시간 포맷팅
def _format_datetime(value) -> tuple[str, str]:
    dt = None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        except ValueError:
            dt = None
    if dt is None:
        return "-", "-"
    return dt.strftime("%m.%d"), dt.strftime("%I:%M %p").lstrip("0")

# 단건 매치 데이터 파싱 및 정규화
# 매치 1건의 원본 데이터에서 K/D/A, ACS, ADR, HS%, 맵/요원/모드 정보를 추출해 
# 프론트엔드가 요구하는 표준 Match Record 객체로 재구성
def _parse_match(match: dict, puuid: str, riot_name: str, riot_tag: str, agents: dict, maps: dict):
    players = _match_players(match)
    me = _find_me(players, puuid, riot_name, riot_tag)
    if me is None:
        return None

    metadata = match.get("metadata") or {}
    stats = me.get("stats") or {}
    damage = stats.get("damage") or {}

    agent_info = me.get("agent") or me.get("character") or {}
    agent_uuid = str(agent_info.get("id") or "").lower()
    agent_name_en = agent_info.get("name") or ""
    agent_meta = agents["by_uuid"].get(agent_uuid) or agents["by_name"].get(agent_name_en.lower())
    agent_ko = (agent_meta or {}).get("name_ko") or agent_name_en or "-"
    role_type = (agent_meta or {}).get("role_type")

    map_name_en = (metadata.get("map") or {}).get("name") or ""
    map_ko = maps.get(map_name_en.lower(), map_name_en or "-")

    queue = metadata.get("queue") or {}
    mode_key = (queue.get("id") or "").lower()
    mode_ko = MODE_LABELS.get(mode_key, queue.get("name") or mode_key or "-")

    date_str, time_str = _format_datetime(metadata.get("started_at"))

    kills = stats.get("kills") or 0
    deaths = stats.get("deaths") or 0
    assists = stats.get("assists") or 0
    kda = round((kills + assists) / deaths, 2) if deaths else float(kills + assists)

    team_id = me.get("team_id") or me.get("team")
    rounds = _team_rounds(match, team_id)
    result, round_score = _match_result(match, team_id, rounds)
    rounds_played = (rounds[0] + rounds[1]) if rounds else None

    acs = round(stats.get("score", 0) / rounds_played) if rounds_played else None
    adr = round(damage.get("dealt", 0) / rounds_played) if rounds_played else None
    shots = (stats.get("headshots") or 0) + (stats.get("bodyshots") or 0) + (stats.get("legshots") or 0)
    hs_pct = round((stats.get("headshots") or 0) / shots * 100) if shots else 0

    record = {
        "mode": mode_ko,
        "map": map_ko,
        "date": date_str,
        "time": time_str,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kda": kda,
        "roundScore": round_score,
        "result": result,
        "hs": hs_pct,
        "adr": adr,
        "acs": acs,
        "agent": agent_ko,
        "season": SEASON_PLACEHOLDER,
        "act": ACT_PLACEHOLDER,
    }
    return record, role_type, mode_key

# 매치별 K/D 값 리스트 계산
# 파싱된 레코드 목록을 순회하며 매치별 Kill / Death 비율 리스트를 생성
def _kd_values(records: list) -> list:
    return [r["kills"] / r["deaths"] if r["deaths"] else float(r["kills"]) for r in records]

# 최근 매치 요약 통계 집계
# 최근 20경기 기록을 토대로 종합 승률, 승/패 판수, 평균 K/D, 평균 ADR을 집계한 딕셔너리를 생성
def _summarize(records: list) -> dict:
    if not records:
        return {"winRate": 0, "wins": 0, "losses": 0, "avgKd": 0, "avgAdr": 0}
    wins = sum(1 for r in records if r["result"] == "win")
    adr_values = [r["adr"] for r in records if r["adr"] is not None]
    kd_values = _kd_values(records)
    return {
        "winRate": round(wins / len(records) * 100),
        "wins": wins,
        "losses": len(records) - wins,
        "avgKd": round(sum(kd_values) / len(kd_values), 2) if kd_values else 0,
        "avgAdr": round(sum(adr_values) / len(adr_values)) if adr_values else 0,
    }

# 게임 모드별 세부 스탯 산출
# 경쟁전, 일반전 등 특정 큐 타입별 평균 킬, HS%, ADR, ACS 등을 집계
# 경쟁전일 경우 티어 라벨을 함께 주입하며, 팀 개념이 없는 데스매치는 승률과 K/D 집계에서 제외
def _mode_stat(mode_key: str, rank_label: str | None, records: list) -> dict:
    stat = {"winRate": None, "hs": 0, "kd": None, "avgKills": 0, "adr": None, "acs": None}
    if mode_key == "competitive":
        stat["rank"] = rank_label

    if not records:
        return stat

    wins = sum(1 for r in records if r["result"] == "win")
    adr_values = [r["adr"] for r in records if r["adr"] is not None]
    acs_values = [r["acs"] for r in records if r["acs"] is not None]
    kd_values = _kd_values(records)

    stat["hs"] = round(sum(r["hs"] for r in records) / len(records))
    stat["avgKills"] = round(sum(r["kills"] for r in records) / len(records), 1)
    stat["adr"] = round(sum(adr_values) / len(adr_values)) if adr_values else None
    stat["acs"] = round(sum(acs_values) / len(acs_values)) if acs_values else None

    # 데스매치는 팀 승패 개념이 없어 승률/K-D는 표시하지 않는다 (mock 데이터와 동일 규칙)
    if mode_key != "deathmatch":
        stat["winRate"] = round(wins / len(records) * 100)
        stat["kd"] = round(sum(kd_values) / len(kd_values), 2) if kd_values else None

    return stat

# 역할군(타격대/척후대 등)별 승률 및 비중 집계
# 유저가 플레이한 요원의 역할군별 승/패 수와 승률을 계산하여 프론트엔드 차트용 데이터 배열로 정렬하여 반환
def _role_distribution(role_results: list) -> list:
    buckets: dict[str, dict] = {}
    for role_type, result in role_results:
        role_ko = ROLE_LABELS.get(role_type)
        if not role_ko:
            continue
        bucket = buckets.setdefault(role_ko, {"role": role_ko, "wins": 0, "losses": 0})
        bucket["wins" if result == "win" else "losses"] += 1

    ordered = []
    for role_ko in ROLE_LABELS.values():
        bucket = buckets.get(role_ko)
        if not bucket:
            continue
        games = bucket["wins"] + bucket["losses"]
        bucket["winRate"] = round(bucket["wins"] / games * 100) if games else 0
        ordered.append(bucket)
    return ordered

# 모스트 요원 TOP N 추출
# 가장 플레이 판수가 많은 요원 순으로 정렬하여 
# 상위 N개 요원의 평균 K/D, ACS, 승률, 승/패 기록을 집계해 반환
def _top_agents(agent_buckets: dict, limit: int = 3) -> list:
    scored = []
    for agent_ko, records in agent_buckets.items():
        if not records or agent_ko == "-":
            continue
        wins = sum(1 for r in records if r["result"] == "win")
        acs_values = [r["acs"] for r in records if r["acs"] is not None]
        kd_values = _kd_values(records)
        scored.append({
            "agent": agent_ko,
            "kd": round(sum(kd_values) / len(kd_values), 2) if kd_values else 0,
            "acs": round(sum(acs_values) / len(acs_values)) if acs_values else 0,
            "winRate": round(wins / len(records) * 100),
            "wins": wins,
            "losses": len(records) - wins,
            "_games": len(records),
        })
    scored.sort(key=lambda a: a["_games"], reverse=True)
    for a in scored:
        a.pop("_games", None)
    return scored[:limit]

# 전체 프로필 데이터 생성 총괄 (Main)
# 참조 데이터 로드 -> 현재 티어 파싱 -> 전체 매치 파싱(에러 발생 시 개별 continue 스킵) 
# -> 모드/역할/요원별 데이터 집계 순으로 프로세스를 수행
# -> 프론트엔드 PlayerProfilePage에 전달할 최종 JSON 딕셔너리를 생성
def build_player_profile(
    db: Session,
    *,
    riot_name: str,
    riot_tag: str,
    puuid: str,
    account: dict | None,
    mmr: dict | None,
    matches_raw: list,
) -> dict:
    agents = _load_ref_agents(db)
    maps = _load_ref_maps(db)

    current = (mmr or {}).get("current") or {}
    rank_label = _translate_rank((current.get("tier") or {}).get("name"))
    current_rr = current.get("rr")
    competitive_rank = f"{rank_label} {current_rr}".strip() if rank_label and current_rr is not None else rank_label

    records: list = []
    role_results: list = []
    mode_buckets: dict[str, list] = {"competitive": [], "unrated": [], "swiftplay": [], "deathmatch": []}
    agent_buckets: dict[str, list] = {}

    for match in matches_raw or []:
        try:
            parsed = _parse_match(match, puuid, riot_name, riot_tag, agents, maps)
        except Exception:
            continue
        if parsed is None:
            continue
        record, role_type, mode_key = parsed
        records.append(record)
        if role_type:
            role_results.append((role_type, record["result"]))
        if mode_key in mode_buckets:
            mode_buckets[mode_key].append(record)
        agent_buckets.setdefault(record["agent"], []).append(record)

    recent = records[:20]

    return {
        "nickname": (account or {}).get("name") or riot_name,
        "tag": (account or {}).get("tag") or riot_tag,
        "level": (account or {}).get("account_level"),
        "title": (account or {}).get("title") or "",
        "lastUpdated": "방금 전",
        "modeStats": {
            key: _mode_stat(key, competitive_rank if key == "competitive" else None, items)
            for key, items in mode_buckets.items()
        },
        "recentSummary": _summarize(recent),
        "roleDistribution": _role_distribution(role_results),
        "topAgents": _top_agents(agent_buckets),
        "matchHistory": records,
    }
