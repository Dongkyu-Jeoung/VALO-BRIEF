"""Prefill compact engagement statistics after signup and compute KAST from API events.

Raw matches and player statistics are no longer inserted or updated here.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from models.team import Team
from services import henrik_api, match_history, team_engagement_cache

TRADE_WINDOW_MS = 5000


def _match_our_side(match: dict, team_name: str, team_tag: str) -> str | None:
    """teams.red/blue 중 roster.name/tag가 조회 대상 팀과 일치하는 쪽을 "red"/"blue"로
    반환 (services/team_profile.py의 동명 함수와 동일 로직).

    roster.get("name")도 strip() 처리한다 - Henrik roster.name에 공백이 붙은 팀이 실제로
    있어(예: "XLA  ") 입력값만 strip하면 비교가 항상 실패한다(ml/engagement_predictor.py::
    _team_roster의 동일 처리 참고)."""
    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for side in ("red", "blue"):
        roster = (teams.get(side) or {}).get("roster") or {}
        if str(roster.get("name", "")).strip().lower() == name_l and str(roster.get("tag", "")).strip().lower() == tag_l:
            return side
    return None


def _group_kills_by_round(kills: list) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for k in kills:
        rnd = k.get("round")
        if rnd is None:
            continue
        grouped.setdefault(rnd, []).append(k)
    for round_kills in grouped.values():
        round_kills.sort(key=lambda k: k.get("kill_time_in_round", 0))
    return grouped


def _compute_player_round_stats(kills_by_round: dict[int, list], puuid: str, rounds_played: int) -> dict:
    """first_bloods/first_deaths/kast/most_used_weapon_uuid를 라운드 단위로 순회하며 계산.
    킬이 하나도 없던 라운드(kills_by_round에 키가 없는 라운드)도 "생존"으로 KAST에
    반영되도록 kills_by_round.items()가 아니라 range(rounds_played) 전체를 순회한다."""
    first_bloods = 0
    first_deaths = 0
    kast_rounds = 0
    weapon_counts: dict[str, int] = {}
    round_events = []

    for rnd in range(rounds_played):
        round_kills = kills_by_round.get(rnd, [])

        if round_kills:
            opening = round_kills[0]
            if opening.get("killer_puuid") == puuid:
                first_bloods += 1
            if opening.get("victim_puuid") == puuid:
                first_deaths += 1

        my_kills = [k for k in round_kills if k.get("killer_puuid") == puuid and k.get("_credit_kill", True)]
        my_death = next((k for k in round_kills if k.get("victim_puuid") == puuid and k.get("_credit_death", True)), None)
        got_assist = any(
            puuid in [a.get("assistant_puuid") for a in (k.get("assistants") or [])]
            for k in round_kills if k.get("_credit_kill", True)
        )
        survived = my_death is None

        # 트레이드 판정: 내가 죽었다면, 나를 죽인 사람이 곧바로(TRADE_WINDOW_MS 이내) 처치됐는지 확인
        traded = False
        if my_death is not None and my_death.get("_credit_kill", True):
            killer_of_me = my_death.get("killer_puuid")
            death_time = my_death.get("kill_time_in_round", 0)
            for k in round_kills:
                if k.get("victim_puuid") == killer_of_me and k.get("_credit_kill", True):
                    revenge_time = k.get("kill_time_in_round", 0)
                    if 0 <= (revenge_time - death_time) <= TRADE_WINDOW_MS:
                        traded = True
                        break

        if my_kills or got_assist or survived or traded:
            kast_rounds += 1

        for k in my_kills:
            weapon_id = str(k.get("damage_weapon_id") or "").lower()
            if weapon_id:
                weapon_counts[weapon_id] = weapon_counts.get(weapon_id, 0) + 1

        if my_kills or my_death is not None or got_assist:
            round_events.append({
                "round": rnd,
                "kills": len(my_kills),
                "death": my_death is not None,
                "assist": got_assist,
                "traded": traded,
            })

    most_used_weapon_uuid = max(weapon_counts, key=weapon_counts.get) if weapon_counts else None

    return {
        "first_bloods": first_bloods,
        "first_deaths": first_deaths,
        "kast_rounds": kast_rounds,
        "most_used_weapon_uuid": most_used_weapon_uuid,
        "round_events": round_events,
    }


async def _backfill_if_needed(db: Session, match_row: Match, our_team_id: str, weapon_uuids: set) -> None:
    """이미 캐싱된 매치를, 그때는 미가입이었던 상대 팀이 나중에 가입하며 다시 만난 경우
    처리. team_id 배정은 Henrik을 다시 부르지 않고도 안전하게 채울 수 있다 - 이 match_id는
    our_team_id의 프리미어 이력에서 나온 것이므로(호출부에서 이미 그 팀 기준으로 필터링됨)
    매치 참가 두 팀 중 하나는 반드시 our_team_id다. team_a_id가 이미 다른 팀으로 확정되어
    있다면 아직 비어있는 team_b_id 쪽이 our_team_id라고 확정할 수 있다.

    이 매치가 services/match_history.py의 write-through 경로(상대팀 검색/승부예측 조회 -
    우리 팀이 가입하기 전에 다른 팀이 이 매치를 먼저 조회해 캐싱했을 수 있음)로 먼저
    저장된 경우, first_bloods/first_deaths/most_used_weapon_uuid/detail_json은 그 경로가
    의도적으로 건드리지 않아(match_history.py 모듈 docstring 참고) NULL로 남아 있다 -
    team_id 배정과 달리 이 값들은 원본 kills 이벤트가 있어야 계산되는데 그건 DB에
    저장돼 있지 않으므로, 이 매치의 어떤 로우든 first_bloods가 비어 있으면 Henrik 매치
    상세를 한 번 다시 불러와 _insert_match과 동일한 방식으로 로스터 전원의 파생 스탯을
    재계산해 채운다."""
    is_new_side = our_team_id not in (match_row.team_a_id, match_row.team_b_id)
    if is_new_side:
        if match_row.team_b_id is not None:
            return  # 양쪽 다 이미 다른 팀으로 채워져 있음 (정상 흐름에선 발생하지 않음) - 방어적으로 무시

        match_row.team_b_id = our_team_id
        if (
            match_row.winner_team_id is None
            and match_row.rounds_won_a is not None
            and match_row.rounds_won_b is not None
            and match_row.rounds_won_b > match_row.rounds_won_a
        ):
            match_row.winner_team_id = our_team_id

        db.query(MatchPlayerStat).filter(
            MatchPlayerStat.match_id == match_row.match_id,
            MatchPlayerStat.team_id.is_(None),
        ).update({"team_id": our_team_id})

    needs_derived_stats = (
        db.query(MatchPlayerStat.stat_id)
        .filter(MatchPlayerStat.match_id == match_row.match_id, MatchPlayerStat.first_bloods.is_(None))
        .first()
        is not None
    )
    if needs_derived_stats:
        try:
            match = await henrik_api.get_match_detail(match_row.match_id)
        except henrik_api.HenrikRateLimitError:
            match = None  # 다음 기회에 - 신규 매치 동기화와 동일하게 조용히 스킵

        if match:
            kills_by_round = _group_kills_by_round(match.get("kills") or [])
            rounds_played = len(match.get("rounds") or [])
            kast_by_puuid = calculate_match_kast(match)
            rows = db.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match_row.match_id).all()
            for row in rows:
                advanced = _compute_player_round_stats(kills_by_round, row.puuid, rounds_played)
                row.first_bloods = advanced["first_bloods"]
                row.first_deaths = advanced["first_deaths"]
                weapon_uuid = advanced["most_used_weapon_uuid"]
                row.most_used_weapon_uuid = weapon_uuid if weapon_uuid in weapon_uuids else None
                row.detail_json = advanced["round_events"]
                if row.puuid in kast_by_puuid:
                    row.kast = kast_by_puuid[row.puuid]

    db.commit()


def calculate_match_kast(match: dict, report=None, reconcile_special=False) -> dict[str, float]:
    """완전한 v2 이벤트가 있는 경우에만 KAST를 계산한다. 없으면 보간하지 않는다."""
    def reject(reason):
        if report is not None:
            report(reason)
        return {}

    rounds = match.get("rounds")
    kills = match.get("kills")
    players = (match.get("players") or {}).get("all_players") or []
    if not isinstance(rounds, list) or not rounds or not isinstance(kills, list) or not players:
        return reject(f"MISSING_DATA rounds_type={type(rounds).__name__} kills_type={type(kills).__name__} players={len(players)}")
    teams = match.get("teams") or {}
    scores = [(teams.get(side) or {}).get("rounds_won") for side in ("red", "blue")]
    if any(not isinstance(score, int) or score < 0 for score in scores) or sum(scores) != len(rounds):
        return reject(f"ROUND_SCORE_MISMATCH scores={scores} rounds={len(rounds)}")
    for event in kills:
        if not isinstance(event, dict):
            return reject("INVALID_KILL_EVENT")
        rnd, when = event.get("round"), event.get("kill_time_in_round")
        if not isinstance(rnd, int) or not 0 <= rnd < len(rounds):
            return reject(f"INVALID_ROUND round={rnd} rounds={len(rounds)}")
        if not isinstance(when, (int, float)) or not 0 <= when < float("inf"):
            return reject(f"INVALID_KILL_TIME round={rnd} time={when}")
        if not event.get("killer_puuid") or not event.get("victim_puuid"):
            return reject(f"MISSING_KILLER_OR_VICTIM round={rnd}")
        if not isinstance(event.get("assistants"), list) or any(
            not isinstance(a, dict) or not a.get("assistant_puuid") for a in event["assistants"]
        ):
            return reject(f"INVALID_ASSISTANTS round={rnd}")
    if reconcile_special:
        sides = {p.get("puuid"): str(p.get("team") or "").lower() for p in players}
        normalized = []
        for event in kills:
            killer, victim = event["killer_puuid"], event["victim_puuid"]
            if killer not in sides or victim not in sides:
                return reject(f"UNKNOWN_EVENT_PLAYER round={event['round']} killer={killer} victim={victim}")
            special = killer == victim or (bool(sides[killer]) and sides[killer] == sides[victim])
            # Work on copies; raw match events remain available for other analyses.
            normalized.append({**event, "_credit_kill": not special, "_credit_death": True})
        for player in players:
            puuid = player.get("puuid")
            deaths = [k for k in normalized if k["victim_puuid"] == puuid]
            specials = [k for k in deaths if not k["_credit_kill"]]
            expected = (player.get("stats") or {}).get("deaths")
            if specials and expected == len(deaths) - len(specials):
                for event in specials:
                    event["_credit_death"] = False
            elif specials and expected != len(deaths):
                return reject(f"AMBIGUOUS_SPECIAL_DEATHS puuid={puuid} stats={expected} events={len(deaths)} special={len(specials)} candidates={[(k['round'], k['kill_time_in_round'], k['killer_puuid']) for k in specials]}")
        adjustments = [k for k in normalized if not k["_credit_kill"]]
        if adjustments and report is not None:
            report(f"SPECIAL_EVENTS_NORMALIZED count={len(adjustments)} retained_deaths={sum(k['_credit_death'] for k in adjustments)}")
        kills = normalized
    # 빈 배열/일부 이벤트 누락을 '전 라운드 생존'으로 오인하지 않도록 집계와 대조한다.
    for player in players:
        puuid, stats = player.get("puuid"), player.get("stats") or {}
        if not puuid:
            return reject("MISSING_PLAYER_PUUID")
        actual = {
            "kills": sum(k["killer_puuid"] == puuid and k.get("_credit_kill", True) for k in kills),
            "deaths": sum(k["victim_puuid"] == puuid and k.get("_credit_death", True) for k in kills),
            # Scoreboard assists can include special events; KAST credit is handled separately.
            "assists": sum(any(a["assistant_puuid"] == puuid for a in k["assistants"]) for k in kills),
        }
        if any(stats.get(key) != value for key, value in actual.items()):
            if report is not None:
                sides = {p.get("puuid"): p.get("team") for p in players}
                seen = set()
                for index, event in enumerate(kills):
                    assistants = [a["assistant_puuid"] for a in event["assistants"]]
                    if puuid not in (event["killer_puuid"], event["victim_puuid"], *assistants):
                        continue
                    killer, victim = event["killer_puuid"], event["victim_puuid"]
                    signature = (event["round"], event["kill_time_in_round"], killer, victim)
                    report(f"EVENT_DETAIL puuid={puuid} index={index} round={event['round']} "
                           f"time={event['kill_time_in_round']} killer={killer} victim={victim} "
                           f"assistants={assistants} weapon={event.get('damage_weapon_id')} "
                           f"suicide={killer == victim} same_team={bool(sides.get(killer)) and sides.get(killer) == sides.get(victim)} "
                           f"credit_kill={event.get('_credit_kill', True)} credit_death={event.get('_credit_death', True)} "
                           f"duplicate_candidate={signature in seen}")
                    seen.add(signature)
            return reject(f"EVENT_STATS_MISMATCH puuid={puuid} stats={ {key: stats.get(key) for key in actual} } events={actual}")
    grouped = _group_kills_by_round(kills)
    return {
        p["puuid"]: round(_compute_player_round_stats(grouped, p["puuid"], len(rounds))["kast_rounds"] / len(rounds) * 100, 1)
        for p in players
    }


def _insert_match(
    db: Session,
    match: dict,
    our_team_id: str,
    team_name: str,
    team_tag: str,
    agent_meta: dict,
    weapon_uuids: set,
    map_uuids: dict,
    started_at_raw: str | None,
) -> None:
    side = _match_our_side(match, team_name, team_tag)
    if side is None:
        return  # 방어적 스킵 - 우리 팀 로스터를 못 찾은 매치(응답 이상)
    opp_side = "blue" if side == "red" else "red"

    metadata = match.get("metadata") or {}
    # Henrik 응답의 실제 필드명은 밑줄 없는 "matchid"다 (실측 확인 - metadata.match_id는
    # 항상 존재하지 않아 여기서 조용히 return되는 바람에 아무 매치도 저장되지 않는 버그가 있었음).
    match_id = metadata.get("matchid")
    if not match_id:
        return

    teams = match.get("teams") or {}
    our_info = teams.get(side) or {}
    opp_info = teams.get(opp_side) or {}

    our_roster = our_info.get("roster") or {}
    opp_roster = opp_info.get("roster") or {}
    opp_team = _find_registered_team(db, opp_roster.get("name"), opp_roster.get("tag"))
    opp_team_id = opp_team.team_id if opp_team else None
    winner_team_id = our_team_id if our_info.get("has_won") else opp_team_id
    # team_engagement_cache 전용 id - services/match_history.py의 동일 처리와 같은 이유
    # (matches.team_b_id는 teams FK가 걸려 있어 미가입 팀이면 None이어야 하지만,
    # team_engagement_cache.team_id는 FK가 없어 Henrik roster.id를 그대로 써도 된다).
    opp_engagement_id = opp_roster.get("id")

    game_start = _parse_game_start(metadata.get("game_start"))

    match_row = Match(match_id=match_id)
    match_row.map_uuid = map_uuids.get(str(metadata.get("map") or "").lower())
    match_row.mode = metadata.get("mode")
    match_row.game_start = game_start
    match_row.team_a_id = our_team_id
    match_row.team_b_id = opp_team_id
    match_row.winner_team_id = winner_team_id
    match_row.rounds_won_a = our_info.get("rounds_won")
    match_row.rounds_won_b = opp_info.get("rounds_won")
    match_row.round_detail_json = match.get("rounds") or []
    match_row.api_source = "henrik"
    match_row.collected_at = _now_kst()
    db.add(match_row)

    our_puuids = set(our_roster.get("members") or [])
    all_players = (match.get("players") or {}).get("all_players") or []
    kills_by_round = _group_kills_by_round(match.get("kills") or [])
    kast_by_puuid = calculate_match_kast(match)
    rounds_played = len(match.get("rounds") or [])
    started_at = _parse_started_at(started_at_raw)

    for player in all_players:
        puuid = player.get("puuid")
        if not puuid:
            continue
        # name/tag가 비어 있으면(비공개 계정 등) 정식 upsert가 None을 반환한다 - 이 경우
        # match_history.py와 동일하게 최소 placeholder라도 넣어서 FK를 만족시키고, 이
        # 선수의 매치 스탯도 손실 없이 그대로 저장되게 한다.
        if upsert_riot_account(db, player) is None:
            _ensure_riot_account_placeholder(db, puuid, player.get("name"), player.get("tag"))

        stat_row = MatchPlayerStat(match_id=match_id, puuid=puuid)
        stat_row.team_id = our_team_id if puuid in our_puuids else opp_team_id
        stat_row.started_at = started_at

        stats = player.get("stats") or {}
        heads = stats.get("headshots") or 0
        bodies = stats.get("bodyshots") or 0
        legs = stats.get("legshots") or 0
        total_shots = heads + bodies + legs

        stat_row.kills = stats.get("kills") or 0
        stat_row.deaths = stats.get("deaths") or 0
        stat_row.assists = stats.get("assists") or 0
        stat_row.headshot_pct = round(heads / total_shots * 100, 1) if total_shots else 0.0
        stat_row.adr = round((player.get("damage_made") or 0) / rounds_played) if rounds_played else None
        stat_row.acs = round((stats.get("score") or 0) / rounds_played) if rounds_played else None

        # .replace("/", "") - Henrik이 "KAY/O"처럼 슬래시 포함 이름을 주는데 ref_agents엔
        # "KAYO"로 저장돼 있어 소문자 변환만으로는 매칭이 안 된다(KAY/O 참가 매치에서
        # agent_uuid가 NULL로 저장되던 버그의 원인으로 실측 확인 - services/team_profile.py의
        # 동일 주석 참고).
        agent = agent_meta.get(str(player.get("character") or "").lower().replace("/", ""))
        stat_row.agent_uuid = (agent or {}).get("uuid")
        stat_row.role_type = ROLE_LABELS.get((agent or {}).get("role_type"))

        advanced = _compute_player_round_stats(kills_by_round, puuid, rounds_played)
        stat_row.first_bloods = advanced["first_bloods"]
        stat_row.first_deaths = advanced["first_deaths"]
        stat_row.kast = kast_by_puuid.get(puuid)
        weapon_uuid = advanced["most_used_weapon_uuid"]
        stat_row.most_used_weapon_uuid = weapon_uuid if weapon_uuid in weapon_uuids else None
        stat_row.detail_json = advanced["round_events"]

        db.add(stat_row)

    db.commit()

    # write-through - services/match_history.py와 동일한 컨벤션으로 team_engagement_cache도
    # 바로 채운다(services/team_engagement_cache.py 모듈 docstring 참고).
    our_won = our_info.get("has_won")
    opp_won = opp_info.get("has_won")
    team_engagement_cache.upsert_match_engagement(
        db, our_team_id, match_id,
        opponent_team_id=opp_engagement_id,
        game_start=game_start,
        trade_rate=engagement_predictor.trade_rate_from_matches([match], team_name, team_tag),
        duelist_acs=engagement_predictor.duelist_acs_from_matches([match], team_name, team_tag),
        win=our_won if isinstance(our_won, bool) else None,
    )
    if opp_engagement_id:
        team_engagement_cache.upsert_match_engagement(
            db, opp_engagement_id, match_id,
            opponent_team_id=our_team_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], opp_roster.get("name", ""), opp_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], opp_roster.get("name", ""), opp_roster.get("tag", "")
            ),
            win=opp_won if isinstance(opp_won, bool) else None,
        )


async def _sync(db: Session, team_id: str, team_name: str, team_tag: str) -> None:
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    league_matches = (history or {}).get("league_matches") or []
    match_ids = [m["id"] for m in league_matches if m.get("id")]
    if not match_ids:
        return
    started_at_by_id = {m["id"]: m.get("started_at") for m in league_matches if m.get("id")}

    agent_meta = _load_agent_meta_by_name(db)
    weapon_uuids = _load_weapon_uuids(db)
    map_uuids = _load_map_uuid_by_name(db)

    for match_id in match_ids:
        existing = db.get(Match, match_id)
        if existing is not None:
            # 이미 캐싱된 매치 - team_id 배정은 Henrik을 다시 안 불러도 되지만, first_bloods
            # 등 파생 스탯이 비어 있으면 _backfill_if_needed 내부에서 그때만 다시 불러온다.
            await _backfill_if_needed(db, existing, team_id, weapon_uuids)
            continue

        try:
            match = await henrik_api.get_match_detail(match_id)
        except henrik_api.HenrikRateLimitError:
            # 남은 매치는 이 팀이 다음에 페이지 조회로 자연스럽게 이어서 채워진다.
            break
        if not match:
            continue

        _insert_match(
            db, match, team_id, team_name, team_tag, agent_meta, weapon_uuids, map_uuids,
            started_at_by_id.get(match_id),
        )


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    """team_name/team_tag로 가입된 teams 행을 찾아 team_id를 반환(services/match_history.py::
    _find_team_id와 동일 로직) - sync_team_match_history가 받는 건 team_name/team_tag뿐이라
    (routers/auth.py::signup이 팀 계정을 막 만든 직후라 team_info["id"]를 그대로 넘길 수도
    있지만, 이 팀이 실제로 커밋됐는지 여기서 다시 한번 확인하는 편이 더 안전하다) 여기서
    직접 조회해 our_team_id를 확정한다."""
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(func.lower(Team.team_name) == team_name.strip().lower(), func.lower(Team.team_tag) == team_tag.strip().lower())
        .first()
    )
    return row[0] if row else None


async def _sync(db: Session, team_id: str, team_name: str, team_tag: str) -> None:
    if not team_engagement_cache.ENGAGEMENT_CACHE_ENABLED:
        return
    history = await henrik_api.get_premier_team_history(team_name, team_tag)
    entries = (history or {}).get("league_matches") or []
    seen = set()
    for entry in entries:
        match_id = entry.get("id")
        if not match_id or match_id in seen:
            continue
        seen.add(match_id)
        if team_engagement_cache.has_match(db, team_id, match_id):
            continue
        try:
            match = await henrik_api.get_match_detail(match_id)
        except henrik_api.HenrikRateLimitError:
            break
        if not match or _match_our_side(match, team_name, team_tag) is None:
            continue
        match_history.upsert_match_engagement_summary(db, match_id, match, entry.get("started_at"))


async def sync_team_match_history(team_name: str, team_tag: str) -> None:
    """Signup entry point: populate only team_engagement_cache."""
    if not team_engagement_cache.ENGAGEMENT_CACHE_ENABLED:
        return
    with SessionLocal() as db:
        team_id = _find_team_id(db, team_name, team_tag)
        if team_id is not None:
            await _sync(db, team_id, team_name, team_tag)
