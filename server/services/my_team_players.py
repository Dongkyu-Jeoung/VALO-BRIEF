"""
로그인한 팀 전용 "우리팀 분석 > 개인 분석" 탭 - 선수 목록 데이터 조립.

services/my_team_stats.py의 playerRanking과 같은 전제로, match_player_stats에 이미
캐싱된 값을 그대로 즉시 집계한다(2026-09-09 사용자 확인: player_stats_summary는 선수
상세 페이지의 무기/히트박스/클러치 등 세부 통계용으로 예약되어 있어 이 목록 데이터와는
용도가 달라 별도 캐시 테이블을 새로 만들지 않기로 함).

프로필 사진(avatar_url)/티어(current_rank)는 riot_accounts에 이미 있는 컬럼이지만
services/match_sync.py의 팀 회원가입 동기화 경로는 이 값들을 채우지 않는다(개인 검색
페이지 경로(routers/players.py)에서만 채워짐). 그래서 이 탭에 처음 들어와 값이 없는
선수(current_rank IS NULL)를 발견하면 그 선수에 한해 Henrik 계정/MMR을 조회해
riot_accounts를 채우고, 성공하면 그 다음부터는 다시 조회하지 않는다(riot_accounts
컬럼 단위의 캐시-어사이드).

로스터 확정 방법(2026-09-14 재설계): 이 프로젝트엔 "현재 로스터"를 담는 고정 테이블이
없다(team_members가 있었으나 완전히 제거됨 - database/valo_brief.sql 상단 주석 참고).
예전엔 match_player_stats.team_id로 조회되는 puuid 중 "이 팀으로 가장 많이 출전한 5명"
(출전 매치 수 기준)을 로스터로 역산했는데, 팀이 오래 활동했을수록 이미 나간 선수/대타가
출전 횟수만 많으면 여전히 로스터로 잡히고 진짜 로스터는 밀려나는 문제가 있었다(실측 -
1stgeneration 팀에서 역산한 5명이 Henrik이 지금 알려주는 실제 로스터 7명과 단 한 명도
안 겹침). 그래서 이제는 henrik_api.get_premier_team()이 주는 "member" 필드(팀이 Henrik에
실제로 등록해둔 지금 이 순간의 로스터, puuid 포함 - 대타/전 멤버 문제가 없음)를 로스터
판별의 유일한 기준으로 쓴다. ACS/KD 등 실측 스탯은 여전히 match_player_stats에서 그
puuid로 매칭해 가져오고, 우리 DB에 매치 기록이 아직 없는 신규 영입 선수는 스탯을
0/None으로 표시한다(기록이 쌓이면 다음 조회부터 자동으로 채워짐).

로스터 조회 캐싱(2026-09-14 추가): get_premier_team() 실시간 호출이 매번 1.5초 안팎(레이트
리밋 걸리면 수십 초) 걸려 "개인 분석" 탭이 느리다는 지적을 받아, 이 응답을 team_id 기준
프로세스 메모리에 무기한 캐싱한다(_roster_cache, _get_team_members 참고) - 신선도보다
속도를 우선한다는 결정. 대신 로스터 자체가 바뀌었을 수 있으니 프론트에 "로스터 새로고침"
버튼을 두어, 누르면 force_refresh=True로 캐시를 무시하고 다시 받아온다.
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.match_player_stat import MatchPlayerStat
from models.riot_account import RiotAccount
from models.team import Team
from services import cosmetics, henrik_api
from services.player_profile import _translate_rank
from services.riot_accounts import upsert_riot_account

_agent_name_by_uuid_cache: dict | None = None


def _load_agent_name_by_uuid(db: Session) -> dict:
    """ref_agents.uuid(소문자) -> 영문 요원명(소문자). front/src/constants/gameData.js의
    agents[].id가 이 영문 소문자 포맷과 동일해 프론트에서 별도 변환 없이 에셋을 찾는다."""
    global _agent_name_by_uuid_cache
    if _agent_name_by_uuid_cache is not None:
        return _agent_name_by_uuid_cache
    rows = db.execute(text("SELECT uuid, display_name FROM ref_agents")).mappings().all()
    _agent_name_by_uuid_cache = {r["uuid"].lower(): r["display_name"].lower() for r in rows}
    return _agent_name_by_uuid_cache


def _ensure_riot_account_placeholder(db: Session, puuid: str, name: str | None, tag: str | None) -> None:
    """member 목록엔 있지만 riot_accounts엔 아직 없는 신규 영입 선수를 위한 최소
    placeholder(services/match_history.py::_ensure_riot_account_placeholder와 동일한
    용도 - 이 파일도 같은 테이블에 관여하므로 독립적으로 재구현). 이게 없으면 이 puuid를
    FK로 참조하는 다른 테이블(insights.target_puuid 등)에 쓰다가 IntegrityError로 죽는다
    (2026-09-14 실측 - 로스터 판별을 match_player_stats 기반에서 Henrik member 기반으로
    바꾸면서, riot_accounts에 없는 신규 영입 선수도 로스터에 포함되기 시작해 처음 발생).
    이미 있으면 건드리지 않는다."""
    if db.get(RiotAccount, puuid) is not None:
        return
    db.add(RiotAccount(puuid=puuid, riot_name=name or "-", riot_tag=tag or "-", region="kr", platform="pc"))


async def _enrich_profile(db: Session, row: RiotAccount) -> None:
    """riot_accounts.current_rank가 비어있는 선수 1명을 Henrik에서 조회해 avatar_url/
    current_rank를 채운다. 레이트리밋 등으로 실패해도 조용히 넘어간다 - current_rank가
    여전히 NULL로 남아 다음 방문 때 다시 시도된다."""
    try:
        account = await henrik_api.get_account(row.riot_name, row.riot_tag)
        if account and account.get("puuid") != row.puuid:
            # Henrik의 팀 로스터(member)와 계정 조회(by-name)가 서로 다른 puuid를 알려주는
            # 경우가 있다(2026-09-14 실측 - "ALEKSANDAR#calm" 로스터 슬롯은 puuid
            # 0f0f07d5...인데, 같은 이름#태그로 계정을 조회하면 Henrik이 전혀 다른 puuid
            # 80b8ce70...를 반환함 - 이름#태그가 다른 계정으로 재사용/이관됐거나 Henrik 내부
            # 캐시 불일치). 이 계정은 이 로스터 멤버(row.puuid)와 무관하므로 그대로 쓰면
            # riot_accounts.uq_riot_accounts_name_tag 유니크 제약과 충돌한다(다른 puuid로
            # 같은 name+tag를 또 저장하려다가 IntegrityError). 이번 회차는 건너뛰고 넘어간다 -
            # row.current_rank는 계속 NULL로 남아 다음 방문 때 다시 시도된다.
            return
        region = (account or {}).get("region") or row.region

        avatar_url = await cosmetics.resolve_card(db, account.get("card")) if account else None
        mmr_history = await henrik_api.get_mmr_history(region, row.riot_name, row.riot_tag)
    except henrik_api.HenrikRateLimitError:
        return

    if not account and not mmr_history:
        return

    upsert_riot_account(
        db,
        account or {"puuid": row.puuid, "name": row.riot_name, "tag": row.riot_tag, "region": region},
        mmr_history,
        avatar_url=avatar_url,
    )


_roster_cache: dict[str, list[dict]] = {}


async def _get_team_members(team: Team, force_refresh: bool) -> list[dict]:
    """Henrik get_premier_team()의 member 목록을 team_id 기준으로 프로세스 메모리에
    캐싱한다(TTL 없음 - 2026-09-14 실측으로 get_premier_team() 호출 자체가 매번 약 1.5초
    걸리고, 레이트리밋에 걸리면 30~60초까지도 걸릴 수 있어 "개인 분석" 탭을 열 때마다
    매번 다시 부르면 그만큼 느려짐). 로스터는 자주 안 바뀌니 신선도보다 속도를 우선하고,
    대신 프론트의 "로스터 새로고침" 버튼(force_refresh=True, routers/my_team.py
    GET /players?refresh=true)을 누르면 캐시를 무시하고 Henrik에서 다시 받아 갱신한다.
    프로세스 재시작 시 캐시는 자연히 비워진다(다음 조회 때 새로 채워짐)."""
    if not force_refresh and team.team_id in _roster_cache:
        return _roster_cache[team.team_id]
    team_info = await henrik_api.get_premier_team(team.team_name, team.team_tag)
    members = (team_info or {}).get("member") or []
    _roster_cache[team.team_id] = members
    return members


async def build_my_team_players(db: Session, team: Team, force_refresh: bool = False) -> list[dict]:
    """로스터는 Henrik get_premier_team()의 "member" 필드로 판별하고(모듈 docstring
    참고), 스탯은 그 puuid로 match_player_stats를 매칭해 채운다."""
    members = await _get_team_members(team, force_refresh)
    if not members:
        return []

    member_puuids = [m.get("puuid") for m in members if m.get("puuid")]

    # riot_accounts에 아직 없는 신규 영입 선수는 최소 placeholder부터 만들어둔다 - 아래
    # accounts 조회와 이후 이 puuid를 참조하는 다른 곳(services/ai_report.py 등)이 항상
    # 유효한 FK 대상을 보게 하기 위함(_ensure_riot_account_placeholder 참고).
    existing_puuids = (
        {r[0] for r in db.query(RiotAccount.puuid).filter(RiotAccount.puuid.in_(member_puuids)).all()}
        if member_puuids else set()
    )
    for member in members:
        puuid = member.get("puuid")
        if puuid and puuid not in existing_puuids:
            _ensure_riot_account_placeholder(db, puuid, member.get("name"), member.get("tag"))
    if len(existing_puuids) < len(member_puuids):
        db.flush()

    stat_rows = (
        db.query(MatchPlayerStat).filter(MatchPlayerStat.puuid.in_(member_puuids)).all()
        if member_puuids else []
    )
    by_puuid: dict[str, list[MatchPlayerStat]] = {}
    for s in stat_rows:
        by_puuid.setdefault(s.puuid, []).append(s)

    accounts = (
        {r.puuid: r for r in db.query(RiotAccount).filter(RiotAccount.puuid.in_(member_puuids)).all()}
        if member_puuids else {}
    )

    missing = [row for row in accounts.values() if row.current_rank is None]
    if missing:
        await asyncio.gather(*(_enrich_profile(db, row) for row in missing))

    agent_names = _load_agent_name_by_uuid(db)

    players = []
    for member in members:
        puuid = member.get("puuid")
        if not puuid:
            continue  # 방어적 스킵 - Henrik 응답 이상으로 puuid가 없는 항목

        # 우리 DB에 매치 기록이 없는 신규 영입 선수는 rows/account가 비어 아래 스탯이
        # 전부 0/None으로 내려간다 - 매치가 쌓이면 다음 조회부터 자동으로 채워진다.
        rows = by_puuid.get(puuid, [])
        account = accounts.get(puuid)

        kills = sum(r.kills or 0 for r in rows)
        deaths = sum(r.deaths or 0 for r in rows)
        hs_values = [r.headshot_pct for r in rows if r.headshot_pct is not None]
        adr_values = [r.adr for r in rows if r.adr is not None]
        acs_values = [r.acs for r in rows if r.acs is not None]

        agent_counts: dict[str, int] = {}
        for r in rows:
            if r.agent_uuid:
                key = r.agent_uuid.lower()
                agent_counts[key] = agent_counts.get(key, 0) + 1
        most_agent_uuid = max(agent_counts, key=agent_counts.get) if agent_counts else None

        role_counts: dict[str, int] = {}
        for r in rows:
            if r.role_type:
                role_counts[r.role_type] = role_counts.get(r.role_type, 0) + 1
        role = max(role_counts, key=role_counts.get) if role_counts else None

        players.append({
            "id": puuid,
            # 우리 DB에 이미 있는 이름(riot_accounts)을 우선하고, 없으면 Henrik member의
            # 이름/태그를 그대로 쓴다 - 둘 다 없을 일은 없다(member는 puuid가 있으면
            # name/tag도 항상 같이 준다).
            "name": account.riot_name if account else member.get("name"),
            "tag": account.riot_tag if account else member.get("tag"),
            "avatarUrl": account.avatar_url if account else None,
            "tier": _translate_rank(account.current_rank) if account else None,
            "role": role,
            "mostAgent": agent_names.get(most_agent_uuid) if most_agent_uuid else None,
            "kd": round(kills / deaths, 2) if deaths else float(kills),
            "hs": round(sum(hs_values) / len(hs_values)) if hs_values else 0,
            "adr": round(sum(adr_values) / len(adr_values)) if adr_values else 0,
            "acs": round(sum(acs_values) / len(acs_values)) if acs_values else 0,
            # account_level은 Henrik 계정 조회가 실제로 성공한 적 있을 때만 채워진다
            # (services/riot_accounts.py::upsert_riot_account) - riot_accounts에 아예
            # 없는 신규 영입 선수도 False. "개인 검색" 자동선택(resolve_personal_search_
            # target)이 이 플래그로 1차 필터링한 뒤 실시간으로 다시 확인한다.
            "resolvable": bool(account and account.account_level is not None),
        })

    players.sort(key=lambda p: p["acs"], reverse=True)
    return players


async def resolve_personal_search_target(db: Session, team: Team) -> dict | None:
    """헤더/메뉴바 "개인 검색"이 이동할 선수를 고른다 - 로스터 중 ACS가 가장 높으면서
    지금 이 순간 Henrik에서 실제로 조회되는 선수.

    build_my_team_players의 "resolvable" 플래그는 "Henrik이 이 계정을 예전에 한 번이라도
    확인해준 적 있는지"만 볼 뿐 실시간 재검증이 아니다 - riot_accounts.riot_name/riot_tag는
    매치 상세(v2/match)에 찍혀 있던 이름을 그대로 캐싱한 값이라, 그 선수가 그 이후 Riot ID
    (닉네임#태그)를 바꿨다면 이 플래그는 여전히 True로 남아있지만 Henrik은 그 옛 이름#태그로
    더는 그 계정을 못 찾는다(2026-09-14 실측 - SPF#FF2 사례, 개인검색 nav가 빈 프로필로
    이동하던 원인). 그래서 여기서는 후보마다 Henrik get_account를 직접 불러 "지금도" 이
    이름#태그로 존재하는지 확인하고, 실패하면 다음으로 ACS가 높은 선수로 넘어간다."""
    players = await build_my_team_players(db, team)
    for player in players:
        if player.get("resolvable") is False:
            continue
        name, tag = player.get("name"), player.get("tag")
        if not name or not tag:
            continue
        try:
            account = await henrik_api.get_account(name, tag)
        except henrik_api.HenrikRateLimitError:
            continue
        if account is not None:
            return {"name": name, "tag": tag}
    return None
