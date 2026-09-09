"""
Henrik 매치 상세(v2/match) 하나를 matches/match_player_stats에 upsert(우리팀 분석 페이지
등 다른 화면이 원본 통계를 그대로 읽을 수 있도록)하고, 동시에 그 매치 하나만의 트레이드
성공률/듀얼리스트 ACS를 계산해 team_engagement_cache에 (team_id, match_id) 행으로도
upsert한다 - 승부예측 분석 탭 ③번(교전 매치업 예측) 모델 학습용 데이터 + "지금 폼" 캐시를
겸한다(server/승부예측_성능_분석.md 11번, services/team_engagement_cache.py 모듈 docstring
참고).

services/match_sync.py(회원가입 시 팀 이력 선동기화)와 같은 matches/match_player_stats
테이블에 쓰므로 컨벤션을 맞춘다:
  - matches.team_a_id/team_b_id는 "red=a/blue=b" 같은 고정 색상 의미가 아니다. 이미 DB에
    있는 매치라면 기존에 어느 슬롯이 red/blue였는지 identity로 확인해서 그 배치를 그대로
    유지하고(스왑 금지), 새 매치면 red->a/blue->b를 기본값으로 쓴다.
  - matches.round_detail_json은 라운드 원본 배열 그대로 저장한다(v2/match의 `rounds`
    필드) - ml/engagement_training.py는 이제 이 테이블을 안 읽으므로 이 필드는 우리팀
    분석 페이지 등 다른 소비처를 위한 것.
  - match_player_stats.side는 더 이상 없다(하프타임마다 공/수가 바뀌어 매치당 값 1개로
    표현이 안 되는 데이터였음) - team_id로만 로스터를 가른다.
  - match_player_stats.role_type은 한글 라벨(services.player_profile.ROLE_LABELS)로
    저장한다(match_sync.py와 동일).

KAST는 match_sync.calculate_match_kast로 원본 이벤트를 검증한 뒤 계산한다.
불완전한 응답은 기존 KAST를 보존한다. first_bloods/first_deaths/
most_used_weapon_uuid/detail_json은 이 저장 경로에서 변경하지 않는다.

"조회하는 김에 항상 쌓기"(opportunistic 캐싱) 전략은 그대로 - 별도 배치 작업 없이
routers/teams.py가 이미 받아온 match_details를 그 자리에서 넘기면 된다. 이 함수가
실패해도 화면 응답 자체는 깨지면 안 되므로, 호출부가 반드시 try/except로 감싸고 실패를
삼켜야 한다(이 함수 자체는 예외를 던질 수 있음 - 의도적으로 조용히 삼키지 않는다,
호출부가 로그를 남길지/무시할지 결정).
"""
from datetime import datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ml import engagement_predictor
from models.match import Match
from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team import Team
from services import team_engagement_cache
from services.player_profile import ROLE_LABELS
from services.match_sync import calculate_match_kast

_ref_map_uuid_cache: dict | None = None
_ref_agent_cache: dict | None = None


def _load_map_uuid_by_name(db: Session) -> dict:
    """ref_maps 참조 테이블을 영문명(소문자) -> uuid로 로드(캐시됨). services/player_
    profile.py의 _load_ref_maps는 이름->한글명만 주고 uuid를 안 줘서 여기서 별도로 뺐다."""
    global _ref_map_uuid_cache
    if _ref_map_uuid_cache is None:
        rows = db.execute(text("SELECT uuid, display_name FROM ref_maps")).mappings().all()
        _ref_map_uuid_cache = {r["display_name"].lower(): r["uuid"] for r in rows}
    return _ref_map_uuid_cache


def _load_agent_info_by_name(db: Session) -> dict:
    """ref_agents 참조 테이블을 영문명(소문자) -> {uuid, role_type}으로 로드(캐시됨)."""
    global _ref_agent_cache
    if _ref_agent_cache is None:
        rows = db.execute(text("SELECT uuid, display_name, role_type FROM ref_agents")).mappings().all()
        _ref_agent_cache = {
            r["display_name"].lower(): {"uuid": r["uuid"], "role_type": r["role_type"]} for r in rows
        }
    return _ref_agent_cache


def _parse_game_start(value) -> datetime | None:
    """metadata.game_start(epoch 초/밀리초)를 datetime으로. services/team_profile.py::
    _parse_datetime과 동일 로직 - private 함수라 의존하지 않고 여기 따로 둠."""
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
    return None


def _parse_started_at(value: str | None) -> datetime | None:
    """프리미어 히스토리 API(league_matches[].started_at)의 ISO 문자열("...Z")을
    datetime으로. _parse_game_start(metadata.game_start, epoch)와는 소스가 다른 별도
    값이라 파싱도 따로 한다."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None)


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    """team_name/team_tag로 가입된 teams 행을 찾아 team_id(=Henrik 프리미어 팀 id)를 반환.
    가입 안 된 팀이면 None. 대소문자 무시 비교(services/match_sync.py::
    _find_registered_team과 동일) - exact match면 대소문자 차이만으로 두 파이프라인이
    같은 팀을 다르게 판정할 수 있었다."""
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(func.lower(Team.team_name) == team_name.strip().lower(), func.lower(Team.team_tag) == team_tag.strip().lower())
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
    문서로 확인할 방법이 없어(server/Henrik-API-전체목록.md가 삭제됨) 추측성 키 이름에
    의존하는 대신 이미 확실한 값을 그대로 받는 쪽을 택했다.
    match_id가 비어있으면 조용히 스킵(방어) - 그 외 실패는 예외를 그대로 던지므로 호출부가
    try/except로 감싸야 한다(모듈 docstring 참고)."""
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

    map_uuid = _load_map_uuid_by_name(db).get(str(metadata.get("map") or "").lower())
    game_start = _parse_game_start(metadata.get("game_start"))
    started_at = _parse_started_at(started_at_raw)
    red_rounds_won = red.get("rounds_won")
    blue_rounds_won = blue.get("rounds_won")
    rounds_played = (red_rounds_won or 0) + (blue_rounds_won or 0)

    # 맵 UUID 캐시 로드 및 파싱
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
        agent_meta = agent_info.get(character.lower())
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

        stat_row.team_id = team_id
        stat_row.is_mvp = (puuid == mvp_puuid) if mvp_puuid else False
        stat_row.agent_uuid = (agent_meta or {}).get("uuid")
        stat_row.role_type = ROLE_LABELS.get((agent_meta or {}).get("role_type"))
        stat_row.started_at = started_at
        stat_row.acs = acs_by_puuid.get(puuid, 0)
        stat_row.kills = stats.get("kills")
        stat_row.deaths = stats.get("deaths")
        stat_row.assists = stats.get("assists")
        stat_row.headshot_pct = round(heads / total_shots * 100, 1) if total_shots else None
        stat_row.adr = round((player.get("damage_made") or 0) / rounds_played) if rounds_played else None
        # 불완전한 응답으로 기존 KAST를 덮어쓰지 않는다.
        if puuid in kast_by_puuid:
            stat_row.kast = kast_by_puuid[puuid]

    db.commit()

    # write-through - 이 매치에 가입 팀이 껴 있으면(red_team_id/blue_team_id) 그 팀의
    # team_engagement_cache를 바로 이 매치 값으로 upsert한다(services/team_engagement_
    # cache.py 모듈 docstring 참고). ENGAGEMENT_CACHE_ENABLED가 False면 내부에서 조용히
    # 스킵된다.
    if red_team_id:
        team_engagement_cache.upsert_match_engagement(
            db, red_team_id, match_id,
            opponent_team_id=blue_team_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], red_roster.get("name", ""), red_roster.get("tag", "")
            ),
        )
    if blue_team_id:
        team_engagement_cache.upsert_match_engagement(
            db, blue_team_id, match_id,
            opponent_team_id=red_team_id,
            game_start=game_start,
            trade_rate=engagement_predictor.trade_rate_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
            duelist_acs=engagement_predictor.duelist_acs_from_matches(
                [match], blue_roster.get("name", ""), blue_roster.get("tag", "")
            ),
        )
