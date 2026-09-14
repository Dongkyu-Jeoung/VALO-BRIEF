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


async def _enrich_profile(db: Session, row: RiotAccount) -> None:
    """riot_accounts.current_rank가 비어있는 선수 1명을 Henrik에서 조회해 avatar_url/
    current_rank를 채운다. 레이트리밋 등으로 실패해도 조용히 넘어간다 - current_rank가
    여전히 NULL로 남아 다음 방문 때 다시 시도된다."""
    try:
        account = await henrik_api.get_account(row.riot_name, row.riot_tag)
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


async def build_my_team_players(db: Session, team: Team) -> list[dict]:
    """로스터는 Henrik get_premier_team()의 "member" 필드로 판별하고(모듈 docstring
    참고), 스탯은 그 puuid로 match_player_stats를 매칭해 채운다."""
    team_info = await henrik_api.get_premier_team(team.team_name, team.team_tag)
    members = (team_info or {}).get("member") or []
    if not members:
        return []

    member_puuids = [m.get("puuid") for m in members if m.get("puuid")]

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
