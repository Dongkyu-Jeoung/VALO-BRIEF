"""
matches/match_player_stats에 이미 조회한 Henrik 매치 상세(v2/match)를 upsert - 승부예측
분석 탭 ③번(교전 매치업 예측) 모델 학습용 데이터 축적(server/승부예측_성능_분석.md 7-2/
7-2-1번). routers/teams.py가 이미 받아온 match_details를 버리지 않고 여기로 넘기면 된다.

"조회하는 김에 항상 쌓기"(opportunistic 캐싱, 7-2-1번 1순위) 전략이라 별도 배치 작업이
필요 없다 - fire-and-forget이 아니라 호출부의 db 세션으로 인라인 upsert한다(요청 하나당
로컬 DB 쓰기 몇 건 정도라 Henrik 네트워크 왕복에 비하면 응답 지연에 미치는 영향이
무시할 만한 수준). 이 함수가 실패해도 화면 응답 자체는 깨지면 안 되므로, 호출부가
반드시 try/except로 감싸고 실패를 삼켜야 한다(아래 upsert_match_history 자체는 예외를
던질 수 있음 - 의도적으로 조용히 삼키지 않는다, 호출부가 로그를 남길지/무시할지 결정).

현재 채우는 컬럼: matches 전체 + match_player_stats의 team_id/is_mvp/agent_uuid/
role_type/side/acs/kills/deaths/assists/headshot_pct/adr. kast/first_bloods/
first_deaths/most_used_weapon_uuid/detail_json은 이번 범위(트레이드 성공률/듀얼리스트
매치업 모델)에 필요 없어 NULL로 남겨둔다 - v2/match에서 이 값들을 정확히 뽑으려면
ml/valorant_git.py::compute_advanced_player_stats(v4/match 대상)와 별개로 트레이드 판정
+ 라운드별 그룹핑 로직을 v2/match 스키마에 맞게 다시 구현해야 하는데, 지금 모델엔
필요하지 않아 범위 밖으로 남긴다.
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.match import Match
from models.match_player_stats import MatchPlayerStats
from models.riot_account import RiotAccount
from models.team import Team

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


def _find_team_id(db: Session, team_name: str, team_tag: str) -> str | None:
    """team_name/team_tag로 가입된 teams 행을 찾아 team_id(=Henrik 프리미어 팀 id)를 반환.
    가입 안 된 팀이면 None(matches.team_a_id/team_b_id가 nullable인 이유 그대로)."""
    if not team_name or not team_tag:
        return None
    row = (
        db.query(Team.team_id)
        .filter(Team.team_name == team_name, Team.team_tag == team_tag)
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


def upsert_match_history(db: Session, match_id: str, match: dict) -> None:
    """match(v2/match 응답 1건)를 matches/match_player_stats에 upsert.

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

    team_a_id = _find_team_id(db, red_roster.get("name", ""), red_roster.get("tag", ""))
    team_b_id = _find_team_id(db, blue_roster.get("name", ""), blue_roster.get("tag", ""))
    winner_team_id = team_a_id if red.get("has_won") else team_b_id if blue.get("has_won") else None

    map_uuid = _load_map_uuid_by_name(db).get(str(metadata.get("map") or "").lower())
    game_start = _parse_game_start(metadata.get("game_start"))
    rounds_won_a = red.get("rounds_won")
    rounds_won_b = blue.get("rounds_won")
    rounds_played = (rounds_won_a or 0) + (rounds_won_b or 0)

    match_row = db.get(Match, match_id)
    if match_row is None:
        match_row = Match(match_id=match_id)
        db.add(match_row)
    match_row.map_uuid = map_uuid
    match_row.mode = metadata.get("mode") or metadata.get("queue")
    match_row.game_start = game_start
    match_row.team_a_id = team_a_id
    match_row.team_b_id = team_b_id
    match_row.winner_team_id = winner_team_id
    match_row.rounds_won_a = rounds_won_a
    match_row.rounds_won_b = rounds_won_b
    # kills(트레이드 판정용 원본)만 저장 - 로스터 소속은 match_player_stats.side로 이미
    # 복원 가능해서 여기 중복 저장할 필요 없음(services/match_history.py 모듈 docstring).
    match_row.round_detail_json = {"kills": match.get("kills") or []}
    match_row.api_source = "v2_match"

    all_players = (match.get("players") or {}).get("all_players") or []
    agent_info = _load_agent_info_by_name(db)

    # riot_accounts placeholder를 먼저 다 만들고 flush - match_player_stats.puuid FK를
    # DB가 강제하는데(모델에는 ForeignKey()를 안 걸어뒀으므로, models/match_player_stats.py
    # 상단 주석 참고) SQLAlchemy가 이 둘의 삽입 순서를 자동으로 보장해주지 않는다. flush를
    # 안 하면 같은 커밋 안에서 match_player_stats INSERT가 riot_accounts INSERT보다 먼저
    # 나가 FK 위반이 날 수 있다(실측으로 확인된 문제).
    for player in all_players:
        puuid = player.get("puuid")
        if puuid:
            _ensure_riot_account_placeholder(db, puuid, player.get("name"), player.get("tag"))
    db.flush()

    # ACS를 먼저 전부 계산해두고, 같은 팀(side) 안에서 최고 ACS 선수를 MVP로 표시한다.
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
            side, team_id, mvp_puuid = "red", team_a_id, mvp_red
        elif puuid in blue_puuids:
            side, team_id, mvp_puuid = "blue", team_b_id, mvp_blue
        else:
            side, team_id, mvp_puuid = None, None, None

        character = player.get("character") or ""
        agent_meta = agent_info.get(character.lower())
        stats = player.get("stats") or {}
        heads = stats.get("headshots") or 0
        bodies = stats.get("bodyshots") or 0
        legs = stats.get("legshots") or 0
        total_shots = heads + bodies + legs

        stat_row = (
            db.query(MatchPlayerStats)
            .filter(MatchPlayerStats.match_id == match_id, MatchPlayerStats.puuid == puuid)
            .first()
        )
        if stat_row is None:
            stat_row = MatchPlayerStats(match_id=match_id, puuid=puuid)
            db.add(stat_row)

        stat_row.team_id = team_id
        stat_row.is_mvp = puuid == mvp_puuid
        stat_row.agent_uuid = (agent_meta or {}).get("uuid")
        stat_row.role_type = (agent_meta or {}).get("role_type")
        stat_row.side = side
        stat_row.acs = acs_by_puuid.get(puuid, 0)
        stat_row.kills = stats.get("kills")
        stat_row.deaths = stats.get("deaths")
        stat_row.assists = stats.get("assists")
        stat_row.headshot_pct = round(heads / total_shots * 100, 1) if total_shots else None
        stat_row.adr = round((player.get("damage_made") or 0) / rounds_played) if rounds_played else None

    db.commit()
