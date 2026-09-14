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

Claude 생성이 실측 20~45초 걸려(Henrik 조회+통계 계산은 4.5초뿐, 대부분
Claude 응답/재시도 시간) 요청-응답으로 동기 대기시키지 않는다 - get_or_start_opponent_
ai_report가 캐시가 없으면 즉시 "generating" 상태로 응답하고, 실제 생성(_generate_and_
save)은 BackgroundTasks로 넘긴다. 프론트(MatchPredictionPage/index.jsx)가 몇 초 간격으로
다시 조회(폴링)해서 완료 여부를 확인한다.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from database.connection import SessionLocal
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

# tactic 항목 개수 범위(우선순위 높은 순서로 2~3개) - services/ai_report.py와 동일 관례.
TACTIC_MIN_ITEMS = 2
TACTIC_MAX_ITEMS = 3


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _normalize_item(data: dict) -> dict:
    """{stat,title,detail} 형태 dict를 프론트 계약 shape으로 정규화. detail이
    문자열(구버전 캐시)이면 1개짜리 리스트로 감싼다. services/ai_report.py의 동명
    함수와 동일 - strengths/weaknesses/tactic을 같은 구조로 맞춰서
    front/.../AiReportCard.jsx(우리팀 분석 탭이 쓰던 컴포넌트)를 그대로 재사용한다."""
    detail = data.get("detail")
    if isinstance(detail, str):
        detail = [detail] if detail else []
    elif not isinstance(detail, list):
        detail = []
    return {
        "stat": data.get("stat", "") or "",
        "title": data.get("title", "") or "",
        "detail": detail,
    }


def _encode_item(item: dict) -> str:
    """strength/weakness 구조화 항목({stat,title,detail})을 insights.content(문자열
    컬럼)에 저장하기 위해 JSON으로 인코딩."""
    return json.dumps(item, ensure_ascii=False)


def _decode_item(content: str) -> dict:
    """strength/weakness 항목 디코딩. 파싱 실패(구조화 이전 구버전 캐시 - 통문장
    문자열)면 content 전체를 detail 1개짜리 항목으로 감싸 폴백한다."""
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "detail" in data:
            return _normalize_item(data)
    except (json.JSONDecodeError, TypeError):
        pass
    return {"stat": "", "title": "", "detail": [content] if content else []}


def _encode_tactic(items: list[dict]) -> str:
    """tactic 리스트({stat,title,detail} 항목 2~3개)를 JSON으로 인코딩."""
    return json.dumps(items, ensure_ascii=False)


def _decode_tactic(content: str) -> list[dict]:
    """tactic 디코딩. 구조화 이전엔 tactic이 통문단 문자열이었다(레거시) - JSON 리스트
    파싱이 안 되거나 빈 리스트면 그 문단 전체를 detail 1개짜리 항목 하나로 감싸 호환한다."""
    try:
        data = json.loads(content)
        if isinstance(data, list):
            items = [_normalize_item(e) for e in data if isinstance(e, dict)]
            if items:
                return items
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"stat": "", "title": "", "detail": [content]}] if content else []


def _validate_stat_item(item, label: str) -> dict:
    """strengths/weaknesses/tactic 공통 shape 검증({stat,title,detail} - stat은
    tactic에서만 비어 있어도 되지만 title과 detail은 항상 필수). detail은 1~2개의
    비어있지 않은 문자열로 이루어진 배열이어야 한다. services/ai_report.py의 동명
    함수와 동일."""
    if not isinstance(item, dict):
        raise ValueError(f"{label}은 객체({{stat,title,detail}})여야 함")
    if not isinstance(item.get("stat"), str):
        raise ValueError(f"{label}.stat 누락/타입 오류")
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        raise ValueError(f"{label}.title 누락/빈 값")

    detail = item.get("detail")
    if (
        not isinstance(detail, list)
        or not (1 <= len(detail) <= 2)
        or not all(isinstance(d, str) and d.strip() for d in detail)
    ):
        raise ValueError(f"{label}.detail은 1~2개의 비어있지 않은 문자열 배열이어야 함")

    return {
        "stat": item["stat"].strip(),
        "title": item["title"].strip(),
        "detail": [d.strip() for d in detail],
    }


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
    intro = pick_analysis = None
    tactic: list[dict] = []
    strengths: list[dict] = []
    weaknesses: list[dict] = []
    phases_by_label: dict[str, dict] = {}
    source = "unknown"

    for r in rows:
        if r.insight_type == "summary":
            intro = r.content
        elif r.insight_type == "strength":
            strengths.append(_decode_item(r.content))
        elif r.insight_type == "weakness":
            weaknesses.append(_decode_item(r.content))
        elif r.insight_type == "strategy":
            tactic = _decode_tactic(r.content)
        elif r.insight_type == "pick_analysis":
            pick_analysis = _decode_item(r.content)
        elif r.insight_type == "source":
            source = r.content
        elif r.insight_type and r.insight_type.startswith("phase:"):
            phases_by_label[r.insight_type.split(":", 1)[1]] = _decode_item(r.content)

    if not intro or not tactic or not pick_analysis or len(strengths) < 3 or len(weaknesses) < 3:
        return None, source
    if any(label not in phases_by_label for label in PHASE_LABELS):
        return None, source

    return {
        "intro": intro,
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "tactic": tactic[:TACTIC_MAX_ITEMS],
        "phases": [{"label": label, **phases_by_label[label]} for label in PHASE_LABELS],
        "opponentPickAnalysis": pick_analysis,
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
                      insight_type="strength", content=_encode_item(s), generated_at=now) for s in report["strengths"]]
    rows += [Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                      insight_type="weakness", content=_encode_item(w), generated_at=now) for w in report["weaknesses"]]
    rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                         insight_type="strategy", content=_encode_tactic(report["tactic"]), generated_at=now))
    rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                         insight_type="pick_analysis", content=_encode_item(report["opponentPickAnalysis"]), generated_at=now))
    for phase in report["phases"]:
        rows.append(Insight(team_id=our_team_id, opponent_team_id=opponent_id, target_type="team",
                             insight_type=f"phase:{phase['label']}", content=_encode_item(phase), generated_at=now))
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
        f'  - "{label}": title="{title}", detail={detail}' for label, title, detail in [
            ("구매 페이즈", "세미 에코 세팅", ["상대 적극적 풀바이 대비", "3라운드 경제 우위 확보"]),
            ("초반 페이즈", "정보 수집 우선", ["상대 초반 스킬 사용 활발", "예측 사격으로 진출 차단"]),
            ("중반 페이즈", "다중 각도 압박", ["상대 사이트 홀딩 약함", "로테이션 지연 유도"]),
            ("후반 페이즈", "포스트플랜트 리테이크", ["상대 설치 후 방어 약함", "느슨한 포지셔닝 카운터"]),
        ]
    )
    system_prompt = (
        "너는 발로란트 프리미어 팀 전술 분석가다. 아래 사용자 메시지에 주어진 통계만 "
        "근거로, 로그인한 우리 팀이 이 상대팀을 상대할 때 참고할 전술 인사이트를 "
        "한국어로 작성하라. 반드시 다음 JSON 스키마와 정확히 일치하는 JSON 객체 "
        "하나만 응답하라(스키마 밖 텍스트/설명/마크다운 금지):\n"
        "{\n"
        '  "intro": string,                    // 상대팀 전반 요약 2~3문장\n'
        '  "strengths": [                       // 상대팀 강점 정확히 3개\n'
        '    {"stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        '  "weaknesses": [                      // 상대팀 약점 정확히 3개, 형식 동일\n'
        '    {"stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        f'  "tactic": [                          // 상대 대응 전술 제안, 우선순위 높은 순서로 '
        f'{TACTIC_MIN_ITEMS}~{TACTIC_MAX_ITEMS}개\n'
        '    {"stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        '  "phases": [                          // 정확히 4개, 아래 순서·label 그대로\n'
        '    {"label": "구매 페이즈", "stat": string, "title": string, "detail": string[]},\n'
        '    {"label": "초반 페이즈", "stat": string, "title": string, "detail": string[]},\n'
        '    {"label": "중반 페이즈", "stat": string, "title": string, "detail": string[]},\n'
        '    {"label": "후반 페이즈", "stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        '  "opponentPickAnalysis": {            // 상대 요원 선택 분석, 형식은 위와 동일\n'
        '    "stat": string, "title": string, "detail": string[]\n'
        "  }\n"
        "}\n"
        f'상대팀의 정식 이름은 "{opponent_name}"이다 - 상대팀을 가리킬 때는 항상 이름 뒤에 '
        f'"팀"을 붙여서 써라(예: "{opponent_label}은 ...", "{opponent_label}의 ..." - 빈 '
        f'괄호나 플레이스홀더 없이, "팀" 없이 이름만 쓰지도 말 것).\n'
        "[선수 랭킹]에 있는 특정 선수 개인을 이름으로 언급할 때는 항상 그 이름 바로 "
        '뒤에 "선수"를 붙여서 써라(예: "Vex 선수", "Vex 선수의 듀얼링이 ..." - 이름만 '
        "툭 나오면 아이디처럼 보여 어색하다. 위 팀 이름 뒤에 \"팀\"을 붙이는 규칙과는 "
        "별개이니 혼동하지 말 것 - 팀 전체를 가리킬 때는 \"팀\", 로스터의 개별 선수를 "
        "가리킬 때는 \"선수\"를 붙인다).\n"
        "strengths/weaknesses/tactic/phases/opponentPickAnalysis의 각 항목은 모두 "
        "stat/title/detail 세 필드로 나눠서 쓰고, 각각 아래 규칙을 지켜라:\n"
        "- stat: 근거가 되는 핵심 수치나 요약값 하나만, 5자 내외로 아주 짧게(예: "
        '"68%", "4개 맵 0승", "타격대 3명"). 여러 수치를 나열하지 마라. '
        "strengths/weaknesses는 예외 없이 stat을 채워야 한다 - 약점(weakness)이라고 "
        "해서 stat을 비우지 마라. stat을 빈 문자열(\"\")로 두는 것은 tactic/phases/"
        "opponentPickAnalysis 항목 중에서 정말로 뒷받침할 단일 수치가 없을 때만 "
        "허용되는 예외다.\n"
        "- title: 그 항목이 무엇에 대한 것인지 5~12자 내외 명사구만(예: \"공격 라운드 "
        '주도권\", \"에코 라운드 대응 강화\"). 숫자를 title에 넣지 마라.\n'
        "- detail: 정확히 1~2개의 짧은 구로 이루어진 문자열 배열. 각 구는 6~14자 "
        "내외이며 반드시 보고서식 개조식으로 끝내라 - 명사형이나 어간+'ㅁ/음'으로 "
        '끝내고("~부족", "~필요", "~시급", "~우수", "~흔들림"), "~다/~한다/~하다/'
        '~합니다"로 끝나는 완결형 문장은 절대 쓰지 마라. stat에 쓴 수치나 그와 동일한 '
        "의미의 표현을 detail 안에서 절대 다시 쓰지 마라 - stat과 detail은 서로 다른 "
        "정보를 담아야 한다(stat=얼마나, detail=왜/무슨 의미).\n"
        "phases의 title/detail은 반드시 \"상대가 [구체적인 경향/데이터]를 보이므로 우리는 "
        "[구체적인 대응 행동]을 한다\"는 인과 구조를 title(대응 행동 요약)과 detail(근거→"
        "행동 1~2구)로 나눠서 표현하라 - 아래 예시와 비슷한 깊이/구체성으로 써라(예시를 "
        "그대로 베끼지 말고 아래 실제 통계에 맞게 새로 작성):\n"
        f"{phase_examples}\n"
        "opponentPickAnalysis는 상대가 타격대/척후대/감시자/전략가 중 어느 역할군을 "
        "중심으로 픽하는지와 그 요원들의 조합이 만드는 시너지(예: 연막+저격, 스킬 연계 "
        "이니시에이팅 등)를 실제 조합 데이터에 근거해 title(핵심 성향 요약 명사구)과 "
        "detail(그 근거·시너지를 1~2구로) 나눠서 표현하라 - 다른 항목들과 형식은 "
        "동일하되, stat에는 그 성향을 뒷받침하는 픽 비중 등의 수치를 넣어라(예: "
        '"타격대 3명", "68% 픽률"). 요원의 역할군은 반드시 사용자 메시지의 [요원 '
        "역할군 참고표]만 근거로 판단하라 - 네 지식으로 추측하지 마라(참고표와 다른 "
        "역할로 잘못 분류하는 경우가 있었다).\n"
        "숫자 사용 규칙(stat 필드도 포함해 모든 필드에 예외 없이 적용): ACS/K·D·A/ADR/킬 수 "
        "같은 원본 스탯 수치나 K/D 비율(예: \"1.05\", \"5.0 KD\")은 절대 인용하지 말고, "
        "승률/성공률/픽률처럼 %(퍼센트)로 표현되는 값만 근거로 써서 서술하라 - 크고 작음은 "
        "정성적으로만 표현."
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
    pick_analysis = _validate_stat_item(data.get("opponentPickAnalysis"), "opponentPickAnalysis")

    # 3개 미만이면 재시도(그만큼 근거가 부족하다는 뜻)하지만, 4개 이상 왔을 때 통째로
    # 재시도하는 건 낭비다 - Claude 호출 한 번이 20초 안팎이라(2026-09-12 실측)
    # "거의 맞는" 응답을 버리고 처음부터 다시 부르면 그 20초가 그대로 또 든다. 앞
    # 3개만 잘라 쓰면 결과 품질은 그대로면서 이 낭비를 없앨 수 있다.
    raw_strengths = data.get("strengths") or []
    raw_weaknesses = data.get("weaknesses") or []
    if len(raw_strengths) < 3:
        raise ValueError(f"strengths는 최소 3개여야 함 (받음: {len(raw_strengths)}개)")
    if len(raw_weaknesses) < 3:
        raise ValueError(f"weaknesses는 최소 3개여야 함 (받음: {len(raw_weaknesses)}개)")
    strengths = [_validate_stat_item(s, f"strengths[{i}]") for i, s in enumerate(raw_strengths[:3])]
    weaknesses = [_validate_stat_item(w, f"weaknesses[{i}]") for i, w in enumerate(raw_weaknesses[:3])]

    raw_tactic = data.get("tactic") or []
    if not (TACTIC_MIN_ITEMS <= len(raw_tactic) <= TACTIC_MAX_ITEMS):
        raise ValueError(
            f"tactic은 {TACTIC_MIN_ITEMS}~{TACTIC_MAX_ITEMS}개여야 함 (받음: {len(raw_tactic)}개)"
        )
    tactic = [_validate_stat_item(t, f"tactic[{i}]") for i, t in enumerate(raw_tactic)]

    phases_raw = data.get("phases") or []
    phase_by_label = {p.get("label"): p for p in phases_raw if isinstance(p, dict)}
    phases = []
    for label in PHASE_LABELS:
        if label not in phase_by_label:
            raise ValueError(f'phases에 "{label}" 누락')
        phases.append({"label": label, **_validate_stat_item(phase_by_label[label], f'phases["{label}"]')})

    return {
        "intro": data["intro"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "tactic": tactic,
        "phases": phases,
        "opponentPickAnalysis": pick_analysis,
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
        {"stat": _pct(round_info.get('attackWinRate')), "title": "공격 라운드 주도권",
         "detail": ["공격 사이드 안정적 운영"]},
        {"stat": _pct(round_info.get('fbWinRate')), "title": "선취킬 후 마무리율",
         "detail": ["라운드 마무리 능력 우수"]},
        {"stat": _pct(round_info.get('pistolWinRate')), "title": "피스톨 라운드 승률",
         "detail": ["초반 자금 확보 능력 우수"]},
    ]
    weaknesses = [
        {"stat": _pct(round_info.get('ecoWinRate')), "title": "에코 라운드 승률",
         "detail": ["경제 열세 시 운영 미흡"]},
        {"stat": _pct(round_info.get('fdLoseRate')), "title": "선취 실점 후 패배율",
         "detail": ["실점 후 만회 능력 시급"]},
        {"stat": _pct(round_info.get('defenseWinRate')), "title": "수비 라운드 승률",
         "detail": ["수비 사이드 조직력 부족"]},
    ]
    tactic = [
        {"stat": "", "title": "약점 구간 집중 공략",
         "detail": ["공수 승률 격차 큰 구간 우선 타겟"]},
        {"stat": "", "title": "AI 연동 정상화 대기",
         "detail": ["구체적 맵·조합 전술 추가 예정"]},
    ]
    phases = [
        {"label": label, "stat": "", "title": "AI 연동 대기",
         "detail": [f"{opponent_label} 성향 맞춤 전술 준비 중"]}
        for label in PHASE_LABELS
    ]
    pick_analysis = {
        "stat": "", "title": "AI 연동 대기",
        "detail": [f"{opponent_label} 역할군 픽 성향 분석 준비 중"],
    }
    return {
        "intro": intro, "strengths": strengths, "weaknesses": weaknesses, "tactic": tactic,
        "phases": phases, "opponentPickAnalysis": pick_analysis,
    }


# (our_team_id, opponent_id) 쌍 중 지금 백그라운드에서 생성 중인 것들 - 이 프로세스
# 안에서만 유효한 메모리 락이다(여러 워커 프로세스로 띄우면 워커별로 따로 논다 - 지금
# uvicorn 단일 프로세스 전제, server/AI_리포트_개발_설계.md 참고). 프론트가 몇 초 간격으로
# 폴링하는 동안 같은 쌍에 대해 Claude를 중복으로 여러 번 부르지 않도록 막는 용도일 뿐이고,
# 실제 "생성됐는지"의 원천 진실은 항상 insights 테이블(DB)이다 - 그래서 서버가 재시작돼
# 이 set이 비워져도 다음 폴링이 다시 정상적으로 새 생성을 시작할 뿐, 데이터가 꼬이지 않는다.
_generating: set[tuple[str, str]] = set()


async def get_or_start_opponent_ai_report(
    db: Session, current: Team, opponent_name: str, opponent_tag: str, background_tasks: BackgroundTasks
) -> dict:
    """진입점 - routers/teams.py::GET /{team_name}/{team_tag}/ai-report가 호출.

    Claude 생성은 실측 20~45초 걸려(Henrik 조회+통계 계산은 4.5초뿐, 대부분은 Claude
    응답 시간과 스키마 검증 실패 시 재시도 비용) 이 함수 안에서 동기로 기다리지 않는다.
    항상 빠르게(수 초 내) 응답하고, 실제 생성은 BackgroundTasks로 넘긴다:

    반환 shape: {"status": "ready", "report": {...}} | {"status": "not_ready"} |
    {"status": "generating"}
      - not_ready: 상대팀이 존재하지 않거나(오타 등) team_engagement_cache에 이 팀
        기준정보가 아직 하나도 없음(한 번도 검색/조회된 적 없음) - 재시도해도 똑같으므로
        프론트가 폴링을 멈춰야 하는 상태.
      - generating: 기준정보는 있는데 신선한 캐시된 리포트가 없어 방금 백그라운드 생성을
        시작했거나(또는 이미 진행 중) - 프론트가 잠시 후 다시 조회해야 하는 상태
        (front/.../MatchPredictionPage/index.jsx의 폴링 참고).
      - ready: 캐시된 리포트를 즉시 반환 - 원래 경로와 동일."""
    opponent_name, opponent_tag = opponent_name.strip(), opponent_tag.strip()
    team_info = await henrik_api.get_premier_team(opponent_name, opponent_tag)
    if team_info is None:
        return {"status": "not_ready"}
    opponent_id = team_info["id"]

    if not _has_cached_data(db, opponent_id):
        return {"status": "not_ready"}

    cached, generated_at, cached_source = _read_cached_report(db, current.team_id, opponent_id)
    latest_match_at = _latest_opponent_match_at(db, opponent_id)
    is_fresh = generated_at and (latest_match_at is None or generated_at >= latest_match_at)
    if cached and cached_source == "claude" and is_fresh:
        return {"status": "ready", "report": cached}

    key = (current.team_id, opponent_id)
    if key not in _generating:
        _generating.add(key)
        background_tasks.add_task(_generate_and_save_task, current.team_id, opponent_name, opponent_tag, opponent_id)
    return {"status": "generating"}


async def _generate_and_save(db: Session, our_team_id: str, opponent_name: str, opponent_tag: str, opponent_id: str) -> None:
    """실제 Claude 생성 - 항상 백그라운드에서만 호출한다(get_or_start_opponent_ai_report
    참고). Henrik 매치 상세 조회는 여기서 다시 하는데(호출부가 이미 한 번 했더라도),
    이 함수가 백그라운드 태스크로 넘어가는 시점엔 원래 요청의 asyncio.gather 결과를
    그대로 넘기기보다 이렇게 독립적으로 다시 조회하는 편이 코드가 단순하고, 어차피
    Henrik 쪽 비용(~4.5초)은 전체 20~45초 중 일부일 뿐이라 다시 불러도 손해가 적다
    (server/승부예측_성능_분석.md 스타일의 "원본 재사용 vs 단순함" 트레이드오프)."""
    current = db.query(Team).filter(Team.team_id == our_team_id).first()
    if current is None:
        return

    team_info, history = await asyncio.gather(
        henrik_api.get_premier_team(opponent_name, opponent_tag),
        henrik_api.get_premier_team_history(opponent_name, opponent_tag),
    )
    if team_info is None:
        return

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
    # generate_with_retry는 동기(블로킹) 함수라 - 여기서도 그냥 부르면 백그라운드 태스크가
    # 이벤트 루프를 20~45초씩 막아서 그동안 서버가 처리 중인 다른 모든 요청이 같이
    # 멈춘다. asyncio.to_thread로 별도 스레드에서 돌린다.
    report = await asyncio.to_thread(
        generate_with_retry, system_prompt, user_prompt, _parse_and_validate, log_prefix="opponent_ai_report"
    )

    source = "claude"
    if report is None:
        report = _fallback_report(our_context, opponent_name, opponent_context)
        source = "fallback"

    _save_report(db, current.team_id, opponent_id, report, source)


async def _generate_and_save_task(our_team_id: str, opponent_name: str, opponent_tag: str, opponent_id: str) -> None:
    """BackgroundTasks 진입점 - 응답 전송 후 실행되므로 요청 스코프 세션(Depends(get_db))을
    재사용하지 않고 직접 세션을 열고 닫는다(services/match_sync.py::sync_team_match_history와
    동일 패턴). 무슨 일이 있어도(Claude 실패든 예외든) _generating에서 이 키를 반드시
    지워야 다음 폴링이 다시 시도할 수 있으므로 finally에서 처리한다."""
    db = SessionLocal()
    try:
        await _generate_and_save(db, our_team_id, opponent_name, opponent_tag, opponent_id)
    except Exception as e:
        print(f"  [opponent_ai_report] 백그라운드 생성 실패: {e}")
    finally:
        _generating.discard((our_team_id, opponent_id))
        db.close()
