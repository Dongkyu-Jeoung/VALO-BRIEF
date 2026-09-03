"""
Henrik API 원본 응답(계정/mmr/매치 이력)을 프론트 PlayerProfilePage가 기대하는 형태로 가공.

매치 데이터는 Henrik v1/stored-matches를 쓴다 (v4/matches보다 매치당 용량이 훨씬 작고
더 긴 과거 이력을 한 번에 준다). stored-matches는 조회 대상 플레이어 관점으로 이미 좁혀진
응답(meta+stats 1세트)이라 v4처럼 참가자 목록에서 나를 찾는 과정이 필요 없다.
필드 존재를 보장할 수 없으므로 전부 방어적으로 .get()하고 매치 1건 파싱 실패는
전체 응답을 깨뜨리지 않도록 스킵한다.
"""

import re
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

# Henrik 매치의 season.short(예: "e11a5")는 Riot 공식 Episode/Act 번호 그대로다(임의 계산 아님).
# 프론트 표시용으로 "Episode 11"/"Act 5"로 풀어 쓰고, mode-stats 조회 시엔 반대로 이 라벨을
# 다시 short 코드로 되돌려 mmr 히스토리(by_season)와 매칭한다.
_SEASON_SHORT_RE = re.compile(r"^e(\d+)a(\d+)$", re.IGNORECASE)


def _parse_season_short(short: str | None) -> tuple[str, str]:
    """"e11a5" -> ("Episode 11", "Act 5"). 형식이 아니면 ("-", "-")."""
    m = _SEASON_SHORT_RE.match((short or "").strip())
    if not m:
        return "-", "-"
    episode, act = m.groups()
    return f"Episode {episode}", f"Act {act}"


def _season_act_to_short(season: str | None, act: str | None) -> str | None:
    """("Episode 11", "Act 5") -> "e11a5" (_parse_season_short의 역변환). 매칭 실패 시 None."""
    if not season or not act:
        return None
    sm = re.match(r"Episode\s+(\d+)", season, re.IGNORECASE)
    am = re.match(r"Act\s+(\d+)", act, re.IGNORECASE)
    if not sm or not am:
        return None
    return f"e{sm.group(1)}a{am.group(1)}"


def _translate_rank(tier_patched: str | None) -> str | None:
    """영문 티어 명칭("Platinum 2")을 한국어("플래티넘 2")로 변환."""
    if not tier_patched:
        return None
    parts = tier_patched.split()
    base_ko = TIER_LABELS.get(parts[0].lower(), parts[0])
    rest = " ".join(parts[1:])
    return f"{base_ko} {rest}".strip()


# ref_agents/ref_maps는 정적 참조 테이블이라(런타임에 안 바뀜) 요청마다 새로 조회할 필요가
# 없다. 개인 프로필/모드별 스탯/팀 프로필 요청마다 매번 DB를 다시 왕복하던 걸 프로세스
# 생존 기간 동안 한 번만 로드해 재사용하도록 캐싱한다.
_ref_agents_cache: dict | None = None
_ref_maps_cache: dict | None = None


def _load_ref_agents(db: Session) -> dict:
    """DB의 요원 참조 테이블을 uuid/영문명 양쪽으로 조회 가능한 딕셔너리로 로드(캐시됨)."""
    global _ref_agents_cache
    if _ref_agents_cache is not None:
        return _ref_agents_cache
    rows = db.execute(text("SELECT uuid, display_name, name_ko, role_type FROM ref_agents")).mappings().all()
    by_uuid, by_name = {}, {}
    for r in rows:
        entry = {"name_ko": r["name_ko"] or r["display_name"], "role_type": r["role_type"]}
        by_uuid[r["uuid"].lower()] = entry
        by_name[r["display_name"].lower()] = entry
    _ref_agents_cache = {"by_uuid": by_uuid, "by_name": by_name}
    return _ref_agents_cache


def _load_ref_maps(db: Session) -> dict:
    """DB의 맵 참조 테이블을 영문명 기준 한글명 딕셔너리로 로드(캐시됨)."""
    global _ref_maps_cache
    if _ref_maps_cache is not None:
        return _ref_maps_cache
    rows = db.execute(text("SELECT display_name, name_ko FROM ref_maps")).mappings().all()
    _ref_maps_cache = {r["display_name"].lower(): (r["name_ko"] or r["display_name"]) for r in rows}
    return _ref_maps_cache


def _parse_datetime(value) -> datetime | None:
    """매치 시각(epoch ms/초 또는 ISO 문자열)을 로컬 시간대 datetime으로 파싱."""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        except ValueError:
            return None
    return None


def _format_datetime(dt: datetime | None) -> tuple[str, str]:
    """datetime을 화면 표시용 (날짜, 시간) 문자열 쌍으로 포맷."""
    if dt is None:
        return "-", "-"
    return dt.strftime("%m.%d"), dt.strftime("%I:%M %p").lstrip("0")


def _parse_match(match: dict, agents: dict, maps: dict):
    """stored-matches 1건을 표준 Match Record로 변환.
    반환: (record, role_type, mode_key). 조회 대상 플레이어 관점 응답이라 참가자 목록에서
    나를 찾을 필요 없이 meta/stats/teams를 바로 읽는다."""
    meta = match.get("meta") or {}
    stats = match.get("stats") or {}
    teams = match.get("teams") or {}

    agent_info = stats.get("character") or {}
    agent_uuid = str(agent_info.get("id") or "").lower()
    agent_name_en = agent_info.get("name") or ""
    agent_meta = agents["by_uuid"].get(agent_uuid) or agents["by_name"].get(agent_name_en.lower())
    agent_ko = (agent_meta or {}).get("name_ko") or agent_name_en or "-"
    role_type = (agent_meta or {}).get("role_type")

    map_name_en = (meta.get("map") or {}).get("name") or ""
    map_ko = maps.get(map_name_en.lower(), map_name_en or "-")

    mode_key = str(meta.get("mode") or "").lower().replace(" ", "")
    mode_ko = MODE_LABELS.get(mode_key, meta.get("mode") or "-")

    season, act = _parse_season_short((meta.get("season") or {}).get("short"))

    started_at = _parse_datetime(meta.get("started_at"))
    date_str, time_str = _format_datetime(started_at)

    kills = stats.get("kills") or 0
    deaths = stats.get("deaths") or 0
    assists = stats.get("assists") or 0
    kda = round((kills + assists) / deaths, 2) if deaths else float(kills + assists)

    my_side = str(stats.get("team") or "").lower()
    opp_side = "red" if my_side == "blue" else "blue"
    my_rounds = teams.get(my_side)
    opp_rounds = teams.get(opp_side)
    if my_rounds is not None and opp_rounds is not None:
        rounds_played = my_rounds + opp_rounds
        round_score = f"{my_rounds}-{opp_rounds}"
        result = "win" if my_rounds > opp_rounds else "lose"
    else:
        rounds_played = None
        round_score = "-"
        result = "lose"

    acs = round(stats.get("score", 0) / rounds_played) if rounds_played else None
    damage = stats.get("damage") or {}
    adr = round(damage.get("made", 0) / rounds_played) if rounds_played else None
    shots = stats.get("shots") or {}
    total_shots = (shots.get("head") or 0) + (shots.get("body") or 0) + (shots.get("leg") or 0)
    hs_pct = round((shots.get("head") or 0) / total_shots * 100) if total_shots else 0

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
        "season": season,
        "act": act,
    }
    return record, role_type, mode_key


def _kd_values(records: list) -> list:
    """레코드별 K/D 값 리스트 (데스가 0이면 킬 수 그대로)."""
    return [r["kills"] / r["deaths"] if r["deaths"] else float(r["kills"]) for r in records]


def _summarize(records: list) -> dict:
    """최근 매치 요약(승률/승패/평균 K-D/ADR) 집계. "최근 20게임 요약" 카드용."""
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


def _mode_stat(mode_key: str, rank_label: str | None, records: list) -> dict:
    """단일 모드(경쟁전/일반/신속플레이/데스매치)의 세부 스탯 카드 데이터 계산.
    필드 기본값은 전부 None - "그 구간에 매치 데이터가 없음"과 "실제로 0"을 구분하기 위함
    (rank/winRate는 mmr_history로 채워지는데 매치 상세가 없을 수 있어서)."""
    stat = {"winRate": None, "hs": None, "kd": None, "avgKills": None, "adr": None, "acs": None}
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

    # 데스매치는 팀 승패 개념이 없어 승률/K-D는 표시하지 않는다
    if mode_key != "deathmatch":
        stat["winRate"] = round(wins / len(records) * 100)
        stat["kd"] = round(sum(kd_values) / len(kd_values), 2) if kd_values else None

    return stat


def _role_distribution(role_results: list) -> list:
    """역할군(타격대/척후대/감시자/전략가)별 승/패, 승률 집계."""
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


def _top_agents(agent_buckets: dict, limit: int = 3) -> list:
    """플레이 판수 기준 모스트 요원 상위 N개의 K/D·ACS·승률 집계."""
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


def _collect(matches_raw: list, agents: dict, maps: dict):
    """매치 원본 리스트를 한 번 순회해 (레코드, 역할결과, 모드버킷, 요원버킷, Act색인)으로 반환.
    build_player_profile 전용 - Henrik이 최신순으로 내려주므로 Act 등장 순서를 그대로
    보존하면 자연히 최신순 정렬이 된다."""
    records: list = []
    role_results: list = []
    mode_buckets: dict[str, list] = {"competitive": [], "unrated": [], "swiftplay": [], "deathmatch": []}
    agent_buckets: dict[str, list] = {}
    act_index: dict[str, list] = {}

    for match in matches_raw or []:
        try:
            parsed = _parse_match(match, agents, maps)
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

        season, act = record["season"], record["act"]
        if season != "-" and act != "-":
            acts = act_index.setdefault(season, [])
            if act not in acts:
                acts.append(act)

    return records, role_results, mode_buckets, agent_buckets, act_index


def _compute_mode_stats(
    matches_raw: list,
    agents: dict,
    maps: dict,
    *,
    mmr_history: dict | None,
    season: str | None,
    act: str | None,
) -> dict:
    """모드별(경쟁전/일반/신속플레이/데스매치) 스탯 계산. build_player_profile과
    build_mode_stats가 공용으로 쓴다. season/act를 주면 그 구간 경기만 집계한다.
    경쟁전 카드의 rank/승률은 가능하면 mmr_history(by_season - Riot이 계산해둔 그 Act의
    최종 티어/전체 판수)로 덮어써서, 매치 상세가 그 Act에 다 안 잡혀 있어도 정확하게 만든다."""
    current_data = (mmr_history or {}).get("current_data") or {}
    rank_label = _translate_rank(current_data.get("currenttierpatched"))
    current_rr = current_data.get("ranking_in_tier")
    competitive_rank = f"{rank_label} {current_rr}".strip() if rank_label and current_rr is not None else rank_label

    mode_buckets: dict[str, list] = {"competitive": [], "unrated": [], "swiftplay": [], "deathmatch": []}
    for match in matches_raw or []:
        try:
            parsed = _parse_match(match, agents, maps)
        except Exception:
            continue
        if parsed is None:
            continue
        record, _role_type, mode_key = parsed
        if season and record["season"] != season:
            continue
        if act and record["act"] != act:
            continue
        if mode_key in mode_buckets:
            mode_buckets[mode_key].append(record)

    result = {
        key: _mode_stat(key, competitive_rank if key == "competitive" else None, items)
        for key, items in mode_buckets.items()
    }

    act_short = _season_act_to_short(season, act)
    season_stat = ((mmr_history or {}).get("by_season") or {}).get(act_short) if act_short else None
    if season_stat and "error" not in season_stat:
        comp = result["competitive"]
        comp["rank"] = _translate_rank(season_stat.get("final_rank_patched")) or comp["rank"]
        games = season_stat.get("number_of_games") or 0
        if games:
            comp["winRate"] = round((season_stat.get("wins") or 0) / games * 100)

    return result


def build_player_profile(
    db: Session,
    *,
    riot_name: str,
    riot_tag: str,
    account: dict | None,
    mmr_history: dict | None,
    matches_raw: list,
) -> dict:
    """PlayerProfilePage가 필요로 하는 전체 프로필 JSON을 조립하는 메인 함수.
    modeStats는 가장 최신 Act(actOptions[0]) 기준으로 미리 계산해서 내려준다 - 프론트가
    첫 렌더에서 /mode-stats를 다시 부르지 않아도 되게 하기 위함."""
    agents = _load_ref_agents(db)
    maps = _load_ref_maps(db)

    records, role_results, _mode_buckets_unused, agent_buckets, act_index = _collect(matches_raw, agents, maps)

    # ProfileHeader의 시즌/Act 선택박스 옵션 (실제 데이터가 있는 조합만, 최신순)
    act_options = [{"season": season, "acts": acts} for season, acts in act_index.items()]

    default_season = act_options[0]["season"] if act_options else None
    default_act = act_options[0]["acts"][0] if act_options else None
    mode_stats = _compute_mode_stats(
        matches_raw, agents, maps, mmr_history=mmr_history, season=default_season, act=default_act
    )

    # 매치 기록(matchHistory)은 Act 필터와 무관하게 항상 최근 20게임만
    recent = records[:20]

    return {
        "nickname": (account or {}).get("name") or riot_name,
        "tag": (account or {}).get("tag") or riot_tag,
        "level": (account or {}).get("account_level"),
        "title": (account or {}).get("title") or "",
        "avatarUrl": (account or {}).get("avatarUrl"),
        "lastUpdated": "방금 전",
        "modeStats": mode_stats,
        "recentSummary": _summarize(recent),
        "roleDistribution": _role_distribution(role_results),
        "topAgents": _top_agents(agent_buckets),
        "matchHistory": recent,
        "actOptions": act_options,
    }


def build_mode_stats(
    db: Session,
    *,
    matches_raw: list,
    mmr_history: dict | None = None,
    season: str | None = None,
    act: str | None = None,
) -> dict:
    """ProfileHeader에서 사용자가 다른 Act를 선택했을 때만 호출되는 /mode-stats 응답 조립.
    기본 선택 Act의 modeStats는 build_player_profile이 이미 내려주므로 여기서 다시 계산하지 않는다."""
    agents = _load_ref_agents(db)
    maps = _load_ref_maps(db)
    return _compute_mode_stats(
        matches_raw, agents, maps, mmr_history=mmr_history, season=season, act=act
    )
