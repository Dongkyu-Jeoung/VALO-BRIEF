"""
회원가입 시 팀 프리미어 매치 이력을 선동기화(Pre-fill)하는 파이프라인.

routers/auth.py의 signup()이 팀 계정 생성 직후 BackgroundTasks로 이 모듈의
sync_team_match_history()를 실행한다 - 매치 상세를 여러 건 순차 호출해야 해서(Henrik
레이트리밋 안에서) 회원가입 응답을 그만큼 기다리게 할 수 없기 때문이다.

파싱 대상 스키마(Henrik v2/match)는 services/team_profile.py가 이미 실사용 중인 필드
(teams.red/blue.roster, players.all_players, 최상위 kills 배열의 killer_puuid/
victim_puuid/round/kill_time_in_round)를 그대로 따른다. first_bloods/first_deaths/kast의
라운드별 계산과 트레이드 판정(5초 윈도)은 ml/valorant_git.py(compute_advanced_player_
stats)의 방식을 그대로 옮긴 것 - 앱 전체에서 "KAST"의 정의를 하나로 맞추기 위함.

matches/match_player_stats에 원본을 저장하는 것과 별개로, services/match_history.py와
같은 컨벤션으로 team_engagement_cache에도 write-through한다(services/team_engagement_
cache.py 모듈 docstring 참고) - 회원가입 직후 첫 승부예측 조회부터 바로 "우리 팀" 값이
채워져 있도록 하기 위함.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from ml import engagement_predictor
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team import Team
from services import henrik_api, team_engagement_cache
from services.player_profile import ROLE_LABELS
from services.riot_accounts import upsert_riot_account
from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))

# 팀원이 죽은 뒤 이 시간(ms) 안에 그 킬러를 처치하면 "트레이드"로 KAST에 반영한다.
# ml/valorant_git.py의 TRADE_WINDOW_MS와 동일한 업계 통용 근사치(공식 정의 아님).
TRADE_WINDOW_MS = 5000

# ref_agents/ref_weapons/ref_maps는 정적 참조 테이블이라 프로세스 생존 기간 동안
# 한 번만 로드해 재사용한다 (services/player_profile.py와 동일 캐싱 전략).
_agent_uuid_cache: dict | None = None
_weapon_uuid_cache: set | None = None
_map_uuid_cache: dict | None = None


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _ensure_riot_account_placeholder(db: Session, puuid: str, name: str | None, tag: str | None) -> None:
    """match_player_stats.puuid FK(NOT NULL, riot_accounts 참조)를 만족시키기 위한 최소
    placeholder. services/match_history.py::_ensure_riot_account_placeholder와 동일한
    용도(두 모듈이 같은 테이블에 쓰므로 컨벤션을 맞춤, private 함수라 독립적으로 재구현).
    이미 있으면 건드리지 않는다. name/tag가 비어 있어도(비공개 계정 등) "-"로 채워서
    이 선수의 매치 스탯이 손실되지 않게 한다 - 나중에 직접 검색되면 upsert_riot_account가
    정확한 값으로 갱신한다."""
    if db.get(RiotAccount, puuid) is not None:
        return
    db.add(RiotAccount(puuid=puuid, riot_name=name or "-", riot_tag=tag or "-", region="kr", platform="pc"))


def _parse_game_start(value) -> datetime | None:
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_KST).replace(tzinfo=None)
    return None


def _parse_started_at(value: str | None) -> datetime | None:
    """프리미어 히스토리 API(league_matches[].started_at)의 ISO 문자열("...Z")을 KST
    datetime으로. matches.game_start(v2/match metadata.game_start, epoch)와는 소스가
    다른 별도 값이라 파싱도 따로 한다."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(_KST).replace(tzinfo=None)


def _load_agent_meta_by_name(db: Session) -> dict:
    """요원 영문명(소문자) -> {"uuid": ref_agents.uuid, "role_type": Duelist/Initiator/...}.
    match.players.all_players[].character가 uuid가 아니라 이름 문자열이라
    (services/team_profile.py에서 이미 확인된 필드) 이름 기준으로 되찾아야 한다."""
    global _agent_uuid_cache
    if _agent_uuid_cache is not None:
        return _agent_uuid_cache
    rows = db.execute(text("SELECT uuid, display_name, role_type FROM ref_agents")).mappings().all()
    _agent_uuid_cache = {
        r["display_name"].lower(): {"uuid": r["uuid"], "role_type": r["role_type"]} for r in rows
    }
    return _agent_uuid_cache


def _load_weapon_uuids(db: Session) -> set:
    """ref_weapons.uuid 전체 집합(소문자). kills[].damage_weapon_id가 valorant-api.com과
    같은 uuid 포맷이라는 전제(ref_weapons 테이블 주석 참고)로 직접 대조하고, 매칭되지
    않으면(포맷이 다르거나 신규 무기) most_used_weapon_uuid를 NULL로 남긴다."""
    global _weapon_uuid_cache
    if _weapon_uuid_cache is not None:
        return _weapon_uuid_cache
    rows = db.execute(text("SELECT uuid FROM ref_weapons")).mappings().all()
    _weapon_uuid_cache = {r["uuid"].lower() for r in rows}
    return _weapon_uuid_cache


def _load_map_uuid_by_name(db: Session) -> dict:
    """맵 영문명(소문자) -> ref_maps.uuid. metadata.map도 character와 마찬가지로 이름
    문자열이라 이름 기준으로 uuid를 되찾아야 한다."""
    global _map_uuid_cache
    if _map_uuid_cache is not None:
        return _map_uuid_cache
    rows = db.execute(text("SELECT uuid, display_name FROM ref_maps")).mappings().all()
    _map_uuid_cache = {r["display_name"].lower(): r["uuid"] for r in rows}
    return _map_uuid_cache


def _match_our_side(match: dict, team_name: str, team_tag: str) -> str | None:
    """teams.red/blue 중 roster.name/tag가 조회 대상 팀과 일치하는 쪽을 "red"/"blue"로
    반환 (services/team_profile.py의 동명 함수와 동일 로직)."""
    teams = match.get("teams") or {}
    name_l, tag_l = team_name.strip().lower(), team_tag.strip().lower()
    for side in ("red", "blue"):
        roster = (teams.get(side) or {}).get("roster") or {}
        if str(roster.get("name", "")).lower() == name_l and str(roster.get("tag", "")).lower() == tag_l:
            return side
    return None


def _find_registered_team(db: Session, name: str | None, tag: str | None) -> Team | None:
    """상대팀 name/tag가 이미 가입된 팀인지 조회. 없으면(대부분의 경우) None -
    matches.team_b_id는 그대로 NULL로 남는다."""
    if not name or not tag:
        return None
    return (
        db.query(Team)
        .filter(func.lower(Team.team_name) == name.strip().lower(), func.lower(Team.team_tag) == tag.strip().lower())
        .first()
    )


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

        my_kills = [k for k in round_kills if k.get("killer_puuid") == puuid]
        my_death = next((k for k in round_kills if k.get("victim_puuid") == puuid), None)
        got_assist = any(
            puuid in [a.get("assistant_puuid") for a in (k.get("assistants") or [])]
            for k in round_kills
        )
        survived = my_death is None

        # 트레이드 판정: 내가 죽었다면, 나를 죽인 사람이 곧바로(TRADE_WINDOW_MS 이내) 처치됐는지 확인
        traded = False
        if my_death is not None:
            killer_of_me = my_death.get("killer_puuid")
            death_time = my_death.get("kill_time_in_round", 0)
            for k in round_kills:
                if k.get("victim_puuid") == killer_of_me:
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


def _backfill_if_needed(db: Session, match_row: Match, our_team_id: str) -> None:
    """이미 캐싱된 매치를, 그때는 미가입이었던 상대 팀이 나중에 가입하며 다시 만난 경우
    처리. Henrik을 다시 부르지 않고도 안전하게 채울 수 있다 - 이 match_id는 our_team_id의
    프리미어 이력에서 나온 것이므로(호출부에서 이미 그 팀 기준으로 필터링됨) 매치 참가
    두 팀 중 하나는 반드시 our_team_id다. team_a_id가 이미 다른 팀으로 확정되어 있다면
    아직 비어있는 team_b_id 쪽이 our_team_id라고 확정할 수 있다."""
    if our_team_id in (match_row.team_a_id, match_row.team_b_id):
        return  # 이미 이 팀 기준으로 처리된 매치
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
    db.commit()


def calculate_match_kast(match: dict) -> dict[str, float]:
    """완전한 v2 이벤트가 있는 경우에만 KAST를 계산한다. 없으면 보간하지 않는다."""
    rounds = match.get("rounds")
    kills = match.get("kills")
    players = (match.get("players") or {}).get("all_players") or []
    if not isinstance(rounds, list) or not rounds or not isinstance(kills, list) or not players:
        return {}
    teams = match.get("teams") or {}
    scores = [(teams.get(side) or {}).get("rounds_won") for side in ("red", "blue")]
    if any(not isinstance(score, int) or score < 0 for score in scores) or sum(scores) != len(rounds):
        return {}
    for event in kills:
        if not isinstance(event, dict):
            return {}
        rnd, when = event.get("round"), event.get("kill_time_in_round")
        if not isinstance(rnd, int) or not 0 <= rnd < len(rounds):
            return {}
        if not isinstance(when, (int, float)) or not 0 <= when < float("inf"):
            return {}
        if not event.get("killer_puuid") or not event.get("victim_puuid"):
            return {}
        if not isinstance(event.get("assistants"), list) or any(
            not isinstance(a, dict) or not a.get("assistant_puuid") for a in event["assistants"]
        ):
            return {}
    # 빈 배열/일부 이벤트 누락을 '전 라운드 생존'으로 오인하지 않도록 집계와 대조한다.
    for player in players:
        puuid, stats = player.get("puuid"), player.get("stats") or {}
        if not puuid:
            return {}
        actual = {
            "kills": sum(k["killer_puuid"] == puuid for k in kills),
            "deaths": sum(k["victim_puuid"] == puuid for k in kills),
            "assists": sum(any(a["assistant_puuid"] == puuid for a in k["assistants"]) for k in kills),
        }
        if any(stats.get(key) != value for key, value in actual.items()):
            return {}
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
        # "KAYO"로 저장돼 있어 소문자 변환만으로는 매칭이 안 됐다(2026-09-11, KAY/O 참가
        # 매치에서 agent_uuid가 계속 NULL로 저장되던 버그의 원인으로 실측 확인 -
        # services/team_profile.py의 동일 주석 참고).
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
    team_engagement_cache.upsert_match_engagement(
        db, our_team_id, match_id,
        opponent_team_id=opp_engagement_id,
        game_start=game_start,
        trade_rate=engagement_predictor.trade_rate_from_matches([match], team_name, team_tag),
        duelist_acs=engagement_predictor.duelist_acs_from_matches([match], team_name, team_tag),
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
            # 이미 캐싱된 매치 - Henrik을 다시 부르지 않고 필요하면 상대팀 쪽만 백필.
            _backfill_if_needed(db, existing, team_id)
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


async def sync_team_match_history(team_name: str, team_tag: str) -> None:
    """회원가입 직후 routers/auth.py가 BackgroundTasks로 실행하는 진입점.
    Depends(get_db) 세션은 요청 생명주기에 묶여 있어 백그라운드 태스크에서 재사용할 수
    없으므로 여기서 별도 세션을 열고 닫는다."""
    db = SessionLocal()
    try:
        team_id = _find_team_id(db, team_name, team_tag)
        if team_id is None:
            return  # 방어적 스킵 - 정상 흐름에선 signup()이 이미 커밋한 뒤라 항상 찾아짐
        await _sync(db, team_id, team_name, team_tag)
    finally:
        db.close()