"""
"승부예측 > AI 리포트" 탭(상대팀 인사이트) 백엔드 - front/src/pages/MatchPredictionPage/
AiReportTab.jsx가 기대하는 shape을 채운다. services/ai_report.py("우리팀 분석 > AI
리포트")와 목적/구조는 같지만 대상이 다르다:

  - ai_report.py: 로그인한 팀 "자신"에 대한 리포트 - DB 캐시(my_team_*)만 읽고 Henrik을
    직접 안 부른다(항상 가입 팀이라 DB에 다 있음).
  - 이 모듈: 로그인한 팀이 검색 중인 "상대팀"에 대한 리포트 - 상대는 미가입일 수 있어
    matches.team_a_id/b_id/team_stats_summary.team_id 같은 FK 제약 있는 컬럼에 못
    들어간다(server/database/valo_brief.sql 참고). 그래서 "상대팀 기준정보가 DB에
    들어갔는가"는 FK 제약이 없는 team_engagement_cache로 확인하고(이 팀을 검색한 적이
    있어 write-through가 최소 한 번은 됐는지 - services/match_history.py 참고), 실제
    분석 재료(라운드 페이즈/맵/조합/선수 랭킹)는 그 순간 Henrik에서 라이브로 받아
    services/team_profile.py::build_team_profile로 계산한다(라이브 "통계"/"분석" 탭이
    쓰는 것과 완전히 같은 함수 - 탭마다 숫자가 어긋나지 않게).

결과 캐싱은 ai_report.py와 같은 insights 테이블(모듈 docstring/AI_리포트_개발_설계.md
참고)을 쓰되, 이번엔 opponent_team_id를 채워서 "우리팀 단독 리포트"(opponent_team_id
IS NULL)와 구분한다. source("claude"/"fallback") 마커와 "새 매치 없으면 재사용, 폴백은
항상 재시도" 정책도 동일하다.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ml import engagement_predictor
from models.insight import Insight
from models.team import Team
from models.team_engagement_cache import TeamEngagementCache
from services import henrik_api, my_team_analysis, my_team_stats, team_profile
from services.claude_client import generate_with_retry
from services.player_profile import ROLE_LABELS, _load_ref_agents

_KST = timezone(timedelta(hours=9))

# phases의 4개 페이즈 - 사용자가 제시한 예시와 동일한 구성/순서.
PHASE_LABELS = ["구매 페이즈", "초반 페이즈", "중반 페이즈", "후반 페이즈"]


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _has_cached_data(db: Session, opponent_id: str) -> bool:
    """상대팀 기준정보가 DB에 들어갔는지 확인 - team_engagement_cache에 이 팀으로
    한 행이라도 있으면(과거에 한 번이라도 검색/조회돼 write-through가 됐다는 뜻)
    True. 없으면 아직 리포트를 만들 재료가 없다는 뜻이라 False(호출부가 "준비 중"
    상태로 처리)."""
    return db.query(TeamEngagementCache).filter(TeamEngagementCache.team_id == opponent_id).first() is not None


def _latest_opponent_match_at(db: Session, opponent_id: str) -> datetime | None:
    row = (
        db.query(TeamEngagementCache.game_start)
        .filter(TeamEngagementCache.team_id == opponent_id, TeamEngagementCache.game_start.isnot(None))
        .order_by(TeamEngagementCache.game_start.desc())
        .first()
    )
    return row[0] if row else None


def _rows_to_report(rows: list[Insight]) -> tuple[dict | None, str]:
    intro = tactic = pick_analysis = None
    strengths: list[str] = []
    weaknesses: list[str] = []
    phases_by_label: dict[str, str] = {}
    source = "unknown"

    for r in rows:
        if r.insight_type == "summary":
            intro = r.content
        elif r.insight_type == "strength":
            strengths.append(r.content)
        elif r.insight_type == "weakness":
            weaknesses.append(r.content)
        elif r.insight_type == "strategy":
            tactic = r.content
        elif r.insight_type == "pick_analysis":
            pick_analysis = r.content
        elif r.insight_type == "source":
            source = r.content
        elif r.insight_type and r.insight_type.startswith("phase:"):
            phases_by_label[r.insight_type.split(":", 1)[1]] = r.content

    if not intro or not tactic or not pick_analysis or len(strengths) < 3 or len(weaknesses) < 3:
        return None, source
    if any(label not in phases_by_label for label in PHASE_LABELS):
        return None, source

    return {
        "intro": intro,
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "tactic": tactic,
        "phases": [{"label": label, "text": phases_by_label[label]} for label in PHASE_LABELS],
        "opponentPickAnalysisText": pick_analysis,
    }, source


def _read_cached_report(db: Session, our_team_id: str, opponent_id: str) -> tuple[dict | None, datetime | None, str]:
    rows = (
        db.query(Insight)
        .filter(Insight.team_id == our_team_id, Insight.opponent_team_id == opponent_id, Insight.target_type == "team")
        .all()
    )
    if not rows:
        return None, None, "unknown"
    generated_at = max((r.generated_at for r in rows), default=None)
    report, source = _rows_to_report(rows)
    return report, generated_at, source


def _save_report(db: Session, our_team_id: str, opponent_id: str, report: dict, source: str) -> None:
    db.query(Insight).filter(
        Insight.team_id == our_team_id, Insight.opponent_team_id == opponent_id, Insight.target_type == "team"
    ).delete()

    now = _now_kst()
    rows = [Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                     insight_type="summary", content=report["intro"], generated_at=now)]
    rows += [Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                      insight_type="strength", content=s, generated_at=now) for s in report["strengths"]]
    rows += [Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                      insight_type="weakness", content=w, generated_at=now) for w in report["weaknesses"]]
    rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                         insight_type="strategy", content=report["tactic"], generated_at=now))
    rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                         insight_type="pick_analysis", content=report["opponentPickAnalysisText"], generated_at=now))
    for phase in report["phases"]:
        rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                             insight_type=f"phase:{phase['label']}", content=phase["text"], generated_at=now))
    rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                         insight_type="source", content=source, generated_at=now))

    db.add_all(rows)
    db.commit()


def _pct(value) -> str:
    return f"{value}%" if isinstance(value, (int, float)) else "정보 없음"


def _agent_role_table(db: Session) -> dict[str, str]:
    """요원 한글명 -> 한글 역할군 라벨(타격대/척후대/감시자/전략가) 참고표 - Claude가
    자기 지식으로 역할을 추측하다 틀리는 것(실사용 관찰 - 예: 네온을 전략가로 착각)을
    막기 위해 프롬프트에 정답표로 그대로 넣어준다."""
    agents = _load_ref_agents(db)
    table: dict[str, str] = {}
    for entry in agents["by_name"].values():
        role = ROLE_LABELS.get(entry.get("role_type"))
        if role:
            table[entry["name_ko"]] = role
    return table


def _build_prompt(our_context: dict, opponent_name: str, opponent_context: dict, agent_roles: dict[str, str]) -> tuple[str, str]:
    opponent_label = f"{opponent_name} 팀"
    phase_examples = "\n".join(
        f'  - "{label}": {desc}' for label, desc in [
            ("구매 페이즈", "상대의 자금/요원 조합을 근거로 이번 라운드에 우리가 어떻게 세팅할지 제안"),
            ("초반 페이즈", "상대가 초반에 스킬을 얼마나 적극적으로 쓰는 조합인지 근거로 초반 교전 여부 제안"),
            ("중반 페이즈", "상대의 사이트 홀딩/감시 성향을 근거로 정보 수집·로테이션 전술 제안"),
            ("후반 페이즈", "상대의 설치 후(포스트 플랜트) 성향을 근거로 리테이크/해체 전술 제안"),
        ]
    )
    system_prompt = (
        "너는 발로란트 프리미어 팀 전술 분석가다. 아래 사용자 메시지에 주어진 통계만 "
        "근거로, 로그인한 우리 팀이 이 상대팀을 상대할 때 참고할 전술 인사이트를 "
        "한국어로 작성하라. 반드시 다음 JSON 스키마와 정확히 일치하는 JSON 객체 "
        "하나만 응답하라(스키마 밖 텍스트/설명/마크다운 금지):\n"
        "{\n"
        '  "intro": string,                    // 상대팀 전반 요약 2~3문장\n'
        '  "strengths": string[3],              // 상대팀 강점 정확히 3개\n'
        '  "weaknesses": string[3],             // 상대팀 약점 정확히 3개\n'
        '  "tactic": string,                    // 상대 대응 전술 제안 1문단\n'
        '  "phases": [                          // 정확히 4개, 아래 순서·label 그대로\n'
        '    {"label": "구매 페이즈", "text": string},\n'
        '    {"label": "초반 페이즈", "text": string},\n'
        '    {"label": "중반 페이즈", "text": string},\n'
        '    {"label": "후반 페이즈", "text": string}\n'
        "  ],\n"
        '  "opponentPickAnalysisText": string   // 상대 요원 선택 분석 1~2문단\n'
        "}\n"
        f'상대팀의 정식 이름은 "{opponent_name}"이다 - 상대팀을 가리킬 때는 항상 이름 뒤에 '
        f'"팀"을 붙여서 써라(예: "{opponent_label}은 ...", "{opponent_label}의 ..." - 빈 '
        f'괄호나 플레이스홀더 없이, "팀" 없이 이름만 쓰지도 말 것).\n'
        "phases의 각 text는 반드시 \"상대가 [구체적인 경향/데이터]를 보이므로 우리는 "
        "[구체적인 대응 행동]을 한다\"는 인과 구조로, 아래 예시와 비슷한 깊이/구체성으로 써라 "
        "(예시 문장을 그대로 베끼지 말고 아래 실제 통계에 맞게 새로 작성):\n"
        f"{phase_examples}\n"
        "opponentPickAnalysisText는 상대가 타격대/척후대/감시자/전략가 중 어느 역할군을 "
        "중심으로 픽하는지, 그리고 그 요원들의 조합이 만드는 시너지(예: 연막+저격, 스킬 "
        "연계 이니시에이팅 등)를 실제 조합 데이터에 근거해 설명하라. 요원의 역할군은 "
        "반드시 사용자 메시지의 [요원 역할군 참고표]만 근거로 판단하라 - 네 지식으로 "
        "추측하지 마라(참고표와 다른 역할로 잘못 분류하는 경우가 있었다).\n"
        "숫자 사용 규칙(모든 필드에 예외 없이 적용): ACS/K·D·A/ADR/킬 수 같은 원본 스탯 "
        "수치나 K/D 비율(예: \"1.05\", \"5.0 KD\")은 절대 인용하지 말고, 승률/성공률/픽률처럼 "
        "%(퍼센트)로 표현되는 값만 근거로 써서 서술하라 - 크고 작음은 정성적으로만 표현."
    )

    our_recent = our_context["stats"].get("recentSummary") or {}
    opponent_recent = opponent_context["profile"].get("recentSummary") or {}
    user_prompt = (
        f"[요원 역할군 참고표(요원명 -> 역할군, 이 표만 근거로 판단할 것)]\n"
        f"{json.dumps(agent_roles, ensure_ascii=False)}\n\n"
        f"[우리 팀 최근 폼]\n{json.dumps(our_recent, ensure_ascii=False)}\n\n"
        f"[우리 팀 라운드 페이즈 통계]\n{json.dumps(our_context['analysis'].get('roundInfo'), ensure_ascii=False)}\n\n"
        f"[{opponent_label} 최근 폼]\n{json.dumps(opponent_recent, ensure_ascii=False)}\n\n"
        f"[{opponent_label} 라운드 페이즈 통계(공격/수비/피스톨/에코 승률, 선취킬/선취死 이후 결과율)]\n"
        f"{json.dumps(opponent_context['profile'].get('roundInfo'), ensure_ascii=False)}\n\n"
        f"[{opponent_label} 맵별 승률]\n{json.dumps(opponent_context['profile'].get('mapWinrates'), ensure_ascii=False)}\n\n"
        f"[{opponent_label} 맵별 상세(선호 사이트, 평균 설치 시점, 요원 조합별 승패)]\n"
        f"{json.dumps(opponent_context['profile'].get('mapInfoByMap'), ensure_ascii=False)}\n\n"
        f"[{opponent_label} 선수 랭킹(ACS 상위, 포지션 포함)]\n"
        f"{json.dumps(opponent_context['profile'].get('playerRanking'), ensure_ascii=False)}\n\n"
        f"[{opponent_label} 트레이드 성공률(%)]\n{opponent_context.get('tradeRate')}\n\n"
        f"[{opponent_label} 듀얼리스트 평균 ACS 대비 우리 팀 대비 유불리]\n"
        f"우리팀 듀얼리스트 관련 지표는 별도로 없음 - {opponent_label} 듀얼리스트 평균 ACS: {opponent_context.get('duelistAcs')}"
    )
    return system_prompt, user_prompt


def _parse_and_validate(raw_json: str) -> dict:
    data = json.loads(raw_json)

    if not isinstance(data.get("intro"), str) or not data["intro"].strip():
        raise ValueError("intro 누락/빈 값")
    if not isinstance(data.get("tactic"), str) or not data["tactic"].strip():
        raise ValueError("tactic 누락/빈 값")
    if not isinstance(data.get("opponentPickAnalysisText"), str) or not data["opponentPickAnalysisText"].strip():
        raise ValueError("opponentPickAnalysisText 누락/빈 값")

    strengths = data.get("strengths") or []
    weaknesses = data.get("weaknesses") or []
    if len(strengths) != 3 or not all(isinstance(s, str) for s in strengths):
        raise ValueError(f"strengths는 정확히 3개여야 함 (받음: {len(strengths)}개)")
    if len(weaknesses) != 3 or not all(isinstance(w, str) for w in weaknesses):
        raise ValueError(f"weaknesses는 정확히 3개여야 함 (받음: {len(weaknesses)}개)")

    phases_raw = data.get("phases") or []
    phase_by_label = {p.get("label"): p.get("text") for p in phases_raw if isinstance(p, dict)}
    for label in PHASE_LABELS:
        if not phase_by_label.get(label):
            raise ValueError(f'phases에 "{label}" 누락')

    return {
        "intro": data["intro"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "tactic": data["tactic"],
        "phases": [{"label": label, "text": phase_by_label[label]} for label in PHASE_LABELS],
        "opponentPickAnalysisText": data["opponentPickAnalysisText"],
    }


def _fallback_report(our_context: dict, opponent_name: str, opponent_context: dict) -> dict:
    """Claude 미설정/호출 실패/파싱 실패 시 결정론적 템플릿 - services/ai_report.py::
    _fallback_report와 같은 철학(실제 숫자는 채우되 문장은 규칙 기반)."""
    opponent_label = f"{opponent_name} 팀"
    profile = opponent_context["profile"]
    round_info = profile.get("roundInfo") or {}
    recent = profile.get("recentSummary") or {}
    total_games = (recent.get("wins", 0) or 0) + (recent.get("losses", 0) or 0)

    intro = (
        f"{opponent_label}은 최근 {total_games}경기 기준 승률 {_pct(recent.get('winRate'))}를 기록 중입니다. "
        f"공격 승률 {_pct(round_info.get('attackWinRate'))}, 수비 승률 {_pct(round_info.get('defenseWinRate'))}입니다."
    )
    strengths = [
        f"공격 승률 {_pct(round_info.get('attackWinRate'))}",
        f"선취 라운드 승리 시 라운드 마무리율(FB Win%) {_pct(round_info.get('fbWinRate'))}",
        f"피스톨 라운드 승률 {_pct(round_info.get('pistolWinRate'))}",
    ]
    weaknesses = [
        f"에코 라운드 승률 {_pct(round_info.get('ecoWinRate'))}",
        f"선취 실점 후 라운드 패배율(FD Lose%) {_pct(round_info.get('fdLoseRate'))}",
        f"수비 승률 {_pct(round_info.get('defenseWinRate'))}",
    ]
    tactic = (
        f"AI 연동이 정상 동작하면 {opponent_label}의 맵/조합 성향까지 반영한 구체적인 대응 전술을 제공합니다. "
        "지금은 상대의 공격/수비 승률 격차가 큰 구간을 우선 공략하는 것을 권장합니다."
    )
    phases = [
        {"label": label, "text": f"AI 연동이 정상 동작하면 {opponent_label}의 실제 성향에 맞춘 {label} 전술을 제공합니다."}
        for label in PHASE_LABELS
    ]
    pick_analysis = f"AI 연동이 정상 동작하면 {opponent_label}의 역할군 픽 성향과 조합 시너지를 분석해 제공합니다."
    return {
        "intro": intro, "strengths": strengths, "weaknesses": weaknesses, "tactic": tactic,
        "phases": phases, "opponentPickAnalysisText": pick_analysis,
    }


async def build_opponent_ai_report(db: Session, current: Team, opponent_name: str, opponent_tag: str) -> dict | None:
    """진입점 - routers/teams.py::GET /{team_name}/{team_tag}/ai-report가 호출.

    1) 상대팀 Henrik id를 확인(라이브 header 조회 1건) - 존재 안 하면 None.
    2) team_engagement_cache에 이 상대팀 행이 하나도 없으면(=한 번도 검색/조회된 적
       없어 기준정보가 DB에 아직 없음) None 반환 - 호출부가 "준비 중"으로 표시.
    3) insights 캐시가 있고 "실제 Claude가 생성한 것"이며 상대팀의 최신 매치보다
       새로 생성된 것이면 그대로 반환.
    4) 아니면 상대팀 매치 상세를 라이브로 받아(routers/teams.py::get_team_analysis와
       동일한 호출) build_team_profile로 통계를 만들고 Claude로 리포트 생성 → 실패하면
       폴백 템플릿 → 어느 쪽이든 insights에 저장."""
    opponent_name, opponent_tag = opponent_name.strip(), opponent_tag.strip()
    # routers/teams.py::get_team_profile/get_team_analysis와 동일한 호출 패턴(team_info+
    # history 병렬 조회) - 캐시 판정(_has_cached_data)에 필요한 opponent_id는 team_info에서
    # 나오므로 history를 먼저 버리지 않고 같이 받아둔다(어차피 곧 다시 쓸 데이터).
    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(opponent_name, opponent_tag),
        henrik_api.get_premier_team_history(opponent_name, opponent_tag),
    )
    if team_info is None:
        return None
    opponent_id = team_info["id"]

    if not _has_cached_data(db, opponent_id):
        return None

    cached, generated_at, cached_source = _read_cached_report(db, current.team_id, opponent_id)
    latest_match_at = _latest_opponent_match_at(db, opponent_id)
    is_fresh = generated_at and (latest_match_at is None or generated_at >= latest_match_at)
    if cached and cached_source == "claude" and is_fresh:
        return cached

    league_matches = (history or {}).get("league_matches") or []
    match_ids = [
        m["id"] for m in sorted(league_matches, key=lambda m: m.get("started_at") or "", reverse=True)[
            : team_profile.MATCH_HISTORY_LIMIT
        ]
        if m.get("id")
    ]
    match_details = list(await asyncio.gather(*(henrik_api.get_match_detail(mid) for mid in match_ids)))

    profile = team_profile.build_team_profile(
        db, team_name=opponent_name, team_tag=opponent_tag, team_info=team_info, match_details=match_details
    )
    opponent_context = {
        "profile": profile,
        "tradeRate": engagement_predictor.trade_rate_from_matches(match_details, opponent_name, opponent_tag),
        "duelistAcs": engagement_predictor.duelist_acs_from_matches(match_details, opponent_name, opponent_tag),
    }
    our_context = {
        "stats": my_team_stats.build_my_team_stats(db, current),
        "analysis": my_team_analysis.build_my_team_analysis(db, current.team_id),
    }

    agent_roles = _agent_role_table(db)
    system_prompt, user_prompt = _build_prompt(our_context, opponent_name, opponent_context, agent_roles)
    report = generate_with_retry(system_prompt, user_prompt, _parse_and_validate, log_prefix="opponent_ai_report")

    source = "claude"
    if report is None:
        report = _fallback_report(our_context, opponent_name, opponent_context)
        source = "fallback"

    _save_report(db, current.team_id, opponent_id, report, source)
    return report
