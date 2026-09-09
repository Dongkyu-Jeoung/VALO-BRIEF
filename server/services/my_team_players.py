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

로스터 확정 방법: 이 프로젝트엔 "현재 로스터"를 담는 고정 테이블이 없다(team_members가
있었으나 완전히 제거됨 - database/valo_brief.sql 상단 주석 참고). match_player_stats.
team_id로 조회되는 puuid는 "이 팀으로 한 번이라도 뛴 적 있는 선수 전체"라 팀이 오래
활동했을수록 대타/영입 교체 인원까지 다 섞여 나온다. services/my_team_stats.py의
playerRanking/services/team_profile.py의 _player_ranking도 같은 문제를 상위 5명만
자르는 방식으로 우회하는데, 거기는 ACS 기준이라 대타가 한 경기 잘하면 실제 로스터를
밀어낼 수 있다. 여기서는 "이 팀으로 가장 많이 출전한 5명"(출전 매치 수 기준)을 로스터로
간주해 더 안정적으로 뽑고, 이 5명으로 추린 뒤에만 Henrik 보강을 호출해 로스터가 아닌
선수 때문에 API를 낭비하지 않는다.
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

# 발로란트 팀 로스터 정원(스타팅 5인). team_members 테이블이 없어 이 값으로 상위 N명을 자른다.
ROSTER_SIZE = 5

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
    stat_rows = db.query(MatchPlayerStat).filter(MatchPlayerStat.team_id == team.team_id).all()
    if not stat_rows:
        return []

    by_puuid: dict[str, list[MatchPlayerStat]] = {}
    for s in stat_rows:
        by_puuid.setdefault(s.puuid, []).append(s)

    # 출전 매치 수가 가장 많은 ROSTER_SIZE명만 로스터로 취급(모듈 docstring 참고).
    roster_puuids = sorted(by_puuid, key=lambda p: len(by_puuid[p]), reverse=True)[:ROSTER_SIZE]

    accounts = {
        r.puuid: r for r in db.query(RiotAccount).filter(RiotAccount.puuid.in_(roster_puuids)).all()
    }

    missing = [row for row in accounts.values() if row.current_rank is None]
    if missing:
        await asyncio.gather(*(_enrich_profile(db, row) for row in missing))

    agent_names = _load_agent_name_by_uuid(db)

    players = []
    for puuid in roster_puuids:
        rows = by_puuid[puuid]
        account = accounts.get(puuid)
        if account is None:
            continue  # 방어적 스킵 - match_player_stats.puuid는 riot_accounts FK라 정상 흐름에선 항상 존재

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
            "name": account.riot_name,
            "tag": account.riot_tag,
            "avatarUrl": account.avatar_url,
            "tier": _translate_rank(account.current_rank),
            "role": role,
            "mostAgent": agent_names.get(most_agent_uuid) if most_agent_uuid else None,
            "kd": round(kills / deaths, 2) if deaths else float(kills),
            "hs": round(sum(hs_values) / len(hs_values)) if hs_values else 0,
            "adr": round(sum(adr_values) / len(adr_values)) if adr_values else 0,
            "acs": round(sum(acs_values) / len(acs_values)) if acs_values else 0,
        })

    players.sort(key=lambda p: p["acs"], reverse=True)
    return players
