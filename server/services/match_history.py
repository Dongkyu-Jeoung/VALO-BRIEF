"""Persist compact engagement statistics without storing raw matches or player rows."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ml import engagement_predictor
from models.team import Team
from services import team_engagement_cache

_KST = timezone(timedelta(hours=9))


def _parse_game_start(value) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(_KST).replace(tzinfo=None)
    return None


def _parse_started_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(_KST).replace(tzinfo=None)


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(
            func.lower(Team.team_name) == team_name.strip().lower(),
            func.lower(Team.team_tag) == team_tag.strip().lower(),
        )
        .first()
    )
    return row[0] if row else None


def _ensure_riot_account_placeholder(db: Session, puuid: str, name: str, tag: str) -> None:
    """match_player_stats.puuid FK(NOT NULL, riot_accounts 참조)를 만족시키기 위한 최소
    placeholder. 이미 있으면(검색/프로필 조회로 이미 캐싱됨) 건드리지 않는다 - region 등
    더 정확한 값을 덮어쓰지 않기 위함. 없으면 region은 'kr'로 우선 채워둔다(이 서비스가
    KR 위주라는 기존 전제, routers/search.py의 _GUESS_REGION과 동일) - 나중에 이 선수가
    직접 검색되면 services/riot_accounts.py::upsert_riot_account가 정확한 값으로 갱신한다."""
    if db.get(RiotAccount, puuid) is not None:
        return
    db.add(RiotAccount(puuid=puuid, riot_name=name or "-", riot_tag=tag or "-", region="kr", platform="pc"))


def _resolve_a_is_red(existing: Match | None, red_team_id: str | None, blue_team_id: str | None) -> bool:
    """matches.team_a_id가 이번 매치에서 red 로스터를 가리켜야 하는지 판정.

    이미 DB에 있는 매치라면(services/match_sync.py가 먼저 채웠을 수 있음) 기존
    team_a_id/team_b_id가 red_team_id/blue_team_id 중 어느 쪽과 identity가 같은지로
    기존 배치를 그대로 유지한다(스왑하면 이미 저장된 rounds_won_a/b·winner_team_id와
    안 맞게 됨). 새 매치거나 판단할 단서가 없으면 기존 기본값(red->a)을 쓴다."""
    if existing is None:
        return True
    if existing.team_a_id is not None:
        if red_team_id and existing.team_a_id == red_team_id:
            return True
        if blue_team_id and existing.team_a_id == blue_team_id:
            return False
    if existing.team_b_id is not None:
        if red_team_id and existing.team_b_id == red_team_id:
            return False
        if blue_team_id and existing.team_b_id == blue_team_id:
            return True
    return True


def upsert_match_history(db: Session, match_id: str, match: dict, started_at_raw: str | None = None) -> None:
    """match(v2/match 응답 1건)를 matches/match_player_stats에 upsert하고,
    team_engagement_cache에도 (team_id, match_id) 행으로 write-through한다.

    match_id는 호출부가 넘겨준다(match dict 내부에서 재추출하지 않음) - routers/teams.py는
    이미 history 조회 단계에서 각 매치의 id를 알고 있고(`get_match_detail(mid)` 호출에
    쓴 바로 그 값), v2/match 응답 내부 metadata에 그 id가 정확히 어떤 키로 들어있는지
    확인할 문서가 없어 추측성 키 이름에 의존하는 대신 이미 확실한 값을 그대로 받는
    쪽을 택했다. match_id가 비어있으면 조용히 스킵(방어) - 그 외 실패는 예외를 그대로
    던지므로 호출부가 try/except로 감싸야 한다(모듈 docstring 참고)."""
    if not match_id:
        return

    metadata = match.get("metadata") or {}
    teams = match.get("teams") or {}
    red = teams.get("red") or {}
    blue = teams.get("blue") or {}
    red_roster = red.get("roster") or {}
    blue_roster = blue.get("roster") or {}
    red_puuids = set(red_roster.get("members") or [])
    blue_puuids = set(blue_roster.get("members") or [])

    red_team_id = _find_team_id(db, red_roster.get("name", ""), red_roster.get("tag", ""))
    blue_team_id = _find_team_id(db, blue_roster.get("name", ""), blue_roster.get("tag", ""))
    winner_team_id = red_team_id if red.get("has_won") else blue_team_id if blue.get("has_won") else None

    # team_engagement_cache 전용 id - matches.team_a_id/b_id/winner_team_id(위 red_team_id/
    # blue_team_id)는 teams.team_id FK가 걸려 있어(models/match.py) 가입 팀이 아니면 반드시
    # None이어야 하지만, team_engagement_cache.team_id는 FK가 없다(models/team_engagement_
    # cache.py 참고). roster.id는 Henrik이 매기는 프리미어 팀 고유 id로, 가입 시 그대로
    # teams.team_id로 쓰므로(routers/auth.py) 가입 팀이면 red_team_id와 항상 같은 값이고,
    # 미가입 팀이어도 항상 값이 있다 - 그래서 여기서는 가입 여부와 무관하게 이 id로
    # team_engagement_cache를 쌓는다("팀 전적 검색"으로 본 모든 팀이 학습 데이터에 반영되게).
    red_engagement_id = red_roster.get("id")
    blue_engagement_id = blue_roster.get("id")

    map_uuid = _load_map_uuid_by_name(db).get(str(metadata.get("map") or "").lower())
    game_start = _parse_game_start(metadata.get("game_start"))
    started_at = _parse_started_at(started_at_raw)
    red_rounds_won = red.get("rounds_won")
    blue_rounds_won = blue.get("rounds_won")
    rounds_played = (red_rounds_won or 0) + (blue_rounds_won or 0)

    map_name = metadata.get("map") or ""
    map_uuid_map = _load_map_uuid_by_name(db)
    map_uuid = map_uuid_map.get(map_name.lower())

    match_row = db.get(Match, match_id)
    a_is_red = _resolve_a_is_red(match_row, red_team_id, blue_team_id)
    proposed_a = red_team_id if a_is_red else blue_team_id
    proposed_b = blue_team_id if a_is_red else red_team_id
    rounds_won_a = red_rounds_won if a_is_red else blue_rounds_won
    rounds_won_b = blue_rounds_won if a_is_red else red_rounds_won

    if match_row is None:
        match_row = Match(match_id=match_id)
        db.add(match_row)

    # 이미 알고 있던 팀 id를 이번 조회 결과(예: 조회 실패)로 덮어써서 None으로 되돌리지 않는다
    match_row.team_a_id = proposed_a if proposed_a is not None else match_row.team_a_id
    match_row.team_b_id = proposed_b if proposed_b is not None else match_row.team_b_id
    match_row.winner_team_id = winner_team_id if winner_team_id is not None else match_row.winner_team_id
    match_row.map_uuid = map_uuid
    match_row.mode = metadata.get("mode") or metadata.get("queue")
    match_row.game_start = game_start
    match_row.rounds_won_a = rounds_won_a
    match_row.rounds_won_b = rounds_won_b
    # 라운드 원본 배열 그대로 저장(services/match_sync.py와 동일 형식).
    match_row.round_detail_json = match.get("rounds") or []
    match_row.api_source = "henrik"

    all_players = (match.get("players") or {}).get("all_players") or []
    kast_by_puuid = calculate_match_kast(match)
    agent_info = _load_agent_info_by_name(db)

    # riot_accounts placeholder를 먼저 다 만들고 명시적으로 flush - models/match_player_
    # stat.py는 puuid에 ForeignKey("riot_accounts.puuid")를 걸어뒀으니 SQLAlchemy가 같은
    # flush 안에서도 riot_accounts INSERT를 먼저 내보내야 정상이지만, 초기 구현(FK 선언이
    # 없던 버전)에서 이 순서가 안 지켜져 FK 위반이 실제로 났었다. 지금은 자동 정렬로도 될
    # 가능성이 높지만, 이미 검증된 안전장치라 굳이 제거하지 않고 명시적 flush를 유지한다.
    for player in all_players:
        puuid = player.get("puuid")
        if puuid:
            _ensure_riot_account_placeholder(db, puuid, player.get("name"), player.get("tag"))
    db.flush()

    # ACS 및 MVP 계산
    acs_by_puuid: dict[str, int] = {}
    for player in all_players:
        puuid = player.get("puuid")
        if not puuid:
            continue
        score = (player.get("stats") or {}).get("score", 0)
        acs_by_puuid[puuid] = round(score / rounds_played) if rounds_played else 0

    def _mvp_puuid(puuids: set[str]) -> str | None:
        candidates = {p: acs_by_puuid.get(p, 0) for p in puuids if p in acs_by_puuid}
        return max(candidates, key=candidates.get) if candidates else None

    # 팀별 킬/데스/어시스트 합산 (팀 평균 KDA 계산용)
    team_stats_summary = {"red": {"kills": 0, "deaths": 0, "assists": 0, "count": 0}, 
                          "blue": {"kills": 0, "deaths": 0, "assists": 0, "count": 0}}
    
    for player in all_players:
        puuid = player.get("puuid")
        if not puuid:
            continue
        stats = player.get("stats") or {}
        p_kills = stats.get("kills") or 0
        p_deaths = stats.get("deaths") or 0
        p_assists = stats.get("assists") or 0

        if puuid in red_puuids:
            team_stats_summary["red"]["kills"] += p_kills
            team_stats_summary["red"]["deaths"] += p_deaths
            team_stats_summary["red"]["assists"] += p_assists
            team_stats_summary["red"]["count"] += 1
        elif puuid in blue_puuids:
            team_stats_summary["blue"]["kills"] += p_kills
            team_stats_summary["blue"]["deaths"] += p_deaths
            team_stats_summary["blue"]["assists"] += p_assists
            team_stats_summary["blue"]["count"] += 1

    # 팀별 평균 KDA 계산
    team_avg_kda = {}
    for t_key in ["red", "blue"]:
        c = team_stats_summary[t_key]["count"] or 1
        t_kills = team_stats_summary[t_key]["kills"]
        t_deaths = team_stats_summary[t_key]["deaths"]
        t_assists = team_stats_summary[t_key]["assists"]

        # 팀 전체 합산 기준 KDA: (총 킬+어시스트)/max(총 데스,1) - 전자스포츠에서 흔히
        # 쓰는 팀 종합 지표.
        team_avg_kda[t_key] = round((t_kills + t_assists) / max(t_deaths, 1), 2)

    mvp_red = _mvp_puuid(red_puuids)
    mvp_blue = _mvp_puuid(blue_puuids)

    for player in all_players:
        puuid = player.get("puuid")
        if not puuid:
            continue

        if puuid in red_puuids:
            team_id, mvp_puuid = red_team_id, mvp_red
        elif puuid in blue_puuids:
            team_id, mvp_puuid = blue_team_id, mvp_blue
        else:
            team_id, mvp_puuid = None, None

        character = player.get("character") or ""
        # .replace("/", "") - Henrik이 "KAY/O"처럼 슬래시 포함 이름을 주는데 ref_agents엔
        # "KAYO"로 저장돼 있어 소문자 변환만으로는 매칭이 안 됐다(agent_uuid가 계속 NULL로
        # 저장되던 버그의 원인 - services/team_profile.py의 동일 주석 참고).
        agent_meta = agent_info.get(character.lower().replace("/", ""))
        stats = player.get("stats") or {}
        heads = stats.get("headshots") or 0
        bodies = stats.get("bodyshots") or 0
        legs = stats.get("legshots") or 0
        total_shots = heads + bodies + legs

        stat_row = (
            db.query(MatchPlayerStat)
            .filter(MatchPlayerStat.match_id == match_id, MatchPlayerStat.puuid == puuid)
            .first()
        )
        if stat_row is None:
            stat_row = MatchPlayerStat(match_id=match_id, puuid=puuid)
            db.add(stat_row)

        kills = stats.get("kills") or 0
        deaths = stats.get("deaths") or 0
        assists = stats.get("assists") or 0

        stat_row.team_id = team_id
        stat_row.is_mvp = (puuid == mvp_puuid) if mvp_puuid else False
        stat_row.agent_uuid = (agent_meta or {}).get("uuid")
        stat_row.role_type = ROLE_LABELS.get((agent_meta or {}).get("role_type"))
        stat_row.started_at = started_at
        stat_row.acs = acs_by_puuid.get(puuid, 0)
        stat_row.kills = kills
        stat_row.deaths = deaths
        stat_row.assists = assists
        
        # 개인별 KDA로 저장한다(위 team_avg_kda는 팀 종합 지표로 별도 계산됨).
        stat_row.kda = round((kills + assists) / max(deaths, 1), 2)
        
        stat_row.headshot_pct = round(heads / total_shots * 100, 1) if total_shots else None
        stat_row.adr = round((player.get("damage_made") or 0) / rounds_played) if rounds_played else None
        # 불완전한 응답으로 기존 KAST를 덮어쓰지 않는다.
        if puuid in kast_by_puuid:
            stat_row.kast = kast_by_puuid[puuid]

    db.commit()

    # write-through - 가입 여부와 무관하게 이 매치에 나온 두 팀 다 team_engagement_cache에
    # 쌓는다(위 red_engagement_id/blue_engagement_id 참고 - services/team_engagement_
    # cache.py 모듈 docstring도 같이 참고). ENGAGEMENT_CACHE_ENABLED가 False면 내부에서
    # 조용히 스킵된다.
    red_won = red.get("has_won")
    blue_won = blue.get("has_won")
    if red_engagement_id:
        team_engagement_cache.upsert_match_engagement(
            db, team_ids[side], match_id,
            opponent_team_id=team_ids[opponent],
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], roster.get("name", ""), roster.get("tag", ""),
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], roster.get("name", ""), roster.get("tag", ""),
            ),
            win=won if isinstance(won, bool) else None,
        )
        saved += 1
    return saved
