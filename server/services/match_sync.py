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

    2026-09-14 버그 수정: roster.get("name")도 strip() 처리 - Henrik roster.name에
    공백이 붙은 팀이 실제로 있어(예: "XLA  ") 입력값만 strip하면 비교가 항상 실패했다
    (ml/engagement_predictor.py::_team_roster의 동일 수정 참고)."""
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
