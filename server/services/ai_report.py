"""
"우리팀 분석 > AI 리포트" 탭 백엔드. AI_리포트_개발_설계.md 참고.

DB에 이미 집계된 우리팀 통계(my_team_stats/my_team_analysis/my_team_players/
my_team_player_detail)를 모아 Claude(Anthropic API)로 팀 전술 리포트를 생성한다 -
아무것도 새로 계산하지 않고 다른 탭이 이미 만든 숫자를 프롬프트 재료로만 쓴다
(다른 탭과 항상 같은 숫자를 보장하기 위함).

2026-09-11: 최초 구현은 OpenAI(gpt-4o-mini)였으나 해당 계정에 크레딧이 없어(429
insufficient_quota, 실측 확인) 엔진을 Claude로 교체했다 - AI_리포트_개발_설계.md
9-6번 참고. 데이터 파이프라인/캐싱/폴백 로직은 엔진 교체와 무관하게 전부 그대로다.

2026-09-11(2차): strengths/weaknesses/playerFeedback.strength/weakness를 통문장
string에서 {stat,title,detail} 객체로 구조화했다 - 프론트에서 숫자와 설명을 분리해
카드형으로 보여주기 위함(가독성 이슈, AI_리포트_개발_설계.md 4-2번 갱신). insights
테이블에는 이 객체를 JSON 문자열로 인코딩해 content 컬럼에 그대로 저장한다(스키마
마이그레이션 없이 자유 텍스트 컬럼을 재활용) - _encode_item/_decode_item 참고.

2026-09-11(3차): detail 문장 안에서 stat과 같은 의미의 수치를 또 언급하는 반복 문제가
있어 글자 수 상한과 나쁜 예/좋은 예를 프롬프트에 추가했다.

2026-09-11(4차): 실사용 피드백 - "~이다/~한다"로 끝나는 완결형 문장이 딱딱하고,
detail이 한 줄로 길게 나열되면 읽기 불편하다는 지적. detail을 단일 문자열에서
"개조식(체언/명사형 종결) 구 1~2개로 이루어진 문자열 배열"로 바꿨다. 프론트는 배열의
각 원소를 별도 줄로 렌더링해 자연스러운 줄바꿈을 얻는다(CSS 줄바꿈이나 정규식 분절
대신 구조 자체를 배열로 만든 것 - AI 응답이 매번 달라도 항상 안정적으로 줄이 나뉜다).
구버전 캐시(detail이 문자열이던 시절)는 _decode_item이 1개짜리 배열로 감싸 호환한다.

결과는 insights 테이블(server/database/valo_brief.sql 9번 섹션 - "AI 리포트(Layer2)"
용으로 이미 설계돼 있었으나 이 모듈이 처음 실제로 쓴다)에 문장 단위로 저장한다.
같은 팀으로 재조회하면 새 매치가 안 쌓인 이상 이 캐시를 그대로 재사용해 Claude를
다시 부르지 않는다(비용/레이턴시 문제, AI_리포트_개발_설계.md 5번). 캐시가 있으면
API를 호출하지 않으므로 응답이 즉시 온다 - 스키마를 바꿀 때만(개발 중) 캐시를 지워
재생성을 유도하면 그때만 느려진다(정상 동작, 운영 중엔 매치가 새로 쌓일 때만 발생).

ANTHROPIC_API_KEY가 없거나 호출/파싱이 실패하면 서버가 죽지 않고 결정론적 템플릿
리포트로 대체한다(ml/engagement_predictor.py의 "학습 전 heuristic-v0" 폴백과
같은 철학 - AI_리포트_개발_설계.md 6번).
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.insight import Insight
from models.match import Match
from models.team import Team
from services import my_team_analysis, my_team_player_detail, my_team_players, my_team_stats
from services.environment import load_environment

load_environment()

# 미정 사항(AI_리포트_개발_설계.md 7번) - 비용/응답 품질을 보고 조정 가능하도록 상수로 분리.
# gpt-4o-mini와 비슷한 비용/속도대의 모델 - 품질을 더 원하면 claude-sonnet-5로 교체.
MODEL_NAME = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
# LLM 응답이 스키마를 못 맞추면(로스터 일부 누락 등, 실사용 관찰) 폴백 전에 재시도할 횟수.
CLAUDE_MAX_ATTEMPTS = 3

_KST = timezone(timedelta(hours=9))

# ml/engagement_predictor.py와 동일한 지연 로드 패턴 - 모듈 임포트 시점에 클라이언트를
# 만들면 키가 없는 환경(로컬 개발 등)에서 서버 전체가 못 뜬다.
_client = None
_client_loaded = False


def _get_client():
    global _client, _client_loaded
    if not _client_loaded:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        _client = Anthropic(api_key=api_key) if api_key else None
        _client_loaded = True
    return _client


def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


def _latest_match_at(db: Session, team_id: str) -> datetime | None:
    """이 팀이 참가한 매치 중 가장 최근 game_start. 캐시 신선도 판정용
    (AI_리포트_개발_설계.md 5번 "매치 기반" 기준)."""
    row = (
        db.query(Match.game_start)
        .filter(or_(Match.team_a_id == team_id, Match.team_b_id == team_id))
        .filter(Match.game_start.isnot(None))
        .order_by(Match.game_start.desc())
        .first()
    )
    return row[0] if row else None


def _encode_item(item: dict) -> str:
    """strength/weakness 구조화 항목({stat,title,detail})을 insights.content(문자열
    컬럼)에 저장하기 위해 JSON으로 인코딩. detail이 리스트여도 json.dumps가 그대로
    처리하므로 별도 분기 불필요."""
    return json.dumps(item, ensure_ascii=False)


def _decode_item(content: str) -> dict:
    """strength/weakness 항목 디코딩.
    - detail이 리스트(4차 스키마)면 그대로 사용.
    - detail이 문자열(2~3차 구버전 캐시)이면 1개짜리 리스트로 감싸 호환.
    - JSON 파싱 자체가 실패하면(구조화 이전, 순수 문장 캐시) content 전체를
      1개짜리 detail 리스트로 감싸 폴백한다 - 배포 직후 재생성 전까지 화면이
      깨지지 않게 하기 위함."""
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "detail" in data:
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
    except (json.JSONDecodeError, TypeError):
        pass
    return {"stat": "", "title": "", "detail": [content] if content else []}


def _rows_to_report(rows: list[Insight], roster: list[dict]) -> tuple[dict | None, str]:
    """insights 행들을 프론트 계약 shape으로 재조립. 이전 생성이 중간에 끊겨
    불완전하면(예: 서버 재시작으로 저장 도중 실패) None을 반환해 재생성을 유도한다.
    (report, source) 반환 - source는 "claude"/"fallback"/"unknown"(마커 행이 없던
    구버전 캐시 - 9-8번 참고, _read_cached_report가 신선도 판정에 씀)."""
    intro = tactic = None
    strengths: list[dict] = []
    weaknesses: list[dict] = []
    player_texts: dict[str, dict] = {}
    source = "unknown"

    for r in rows:
        if r.target_type == "team":
            if r.insight_type == "summary":
                intro = r.content
            elif r.insight_type == "strength":
                strengths.append(_decode_item(r.content))
            elif r.insight_type == "weakness":
                weaknesses.append(_decode_item(r.content))
            elif r.insight_type == "strategy":
                tactic = r.content
            elif r.insight_type == "source":
                source = r.content
        elif r.target_type == "player" and r.target_puuid:
            entry = player_texts.setdefault(r.target_puuid, {})
            if r.insight_type in ("strength", "weakness"):
                entry[r.insight_type] = _decode_item(r.content)

    if not intro or not tactic or len(strengths) < 3 or len(weaknesses) < 3:
        return None, source

    player_feedback = []
    for p in roster:
        texts = player_texts.get(p["id"])
        if not texts:
            continue
        player_feedback.append({
            "name": p["name"],
            "role": p.get("role") or "-",
            "acs": p.get("acs", 0),
            "avatarUrl": p.get("avatarUrl"),
            "strength": texts.get("strength") or {"stat": "", "title": "", "detail": []},
            "weakness": texts.get("weakness") or {"stat": "", "title": "", "detail": []},
        })

    if not player_feedback:
        return None, source

    return {
        "intro": intro,
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "tactic": tactic,
        "playerFeedback": player_feedback,
    }, source


def _read_cached_report(db: Session, team_id: str, roster: list[dict]) -> tuple[dict | None, datetime | None, str]:
    rows = (
        db.query(Insight)
        .filter(Insight.team_id == team_id, Insight.opponent_team_id.is_(None))
        .all()
    )
    if not rows:
        return None, None, "unknown"
    generated_at = max((r.generated_at for r in rows), default=None)
    report, source = _rows_to_report(rows, roster)
    return report, generated_at, source


def _save_report(db: Session, team_id: str, report: dict, roster: list[dict], source: str) -> None:
    """이 팀의 기존 팀-리포트 행(opponent_team_id IS NULL)을 전부 지우고 새로 채운다 -
    upsert 키가 없는 문장 단위 테이블이라 "통째로 교체"가 가장 단순하고 안전하다.
    source("claude"/"fallback")는 별도 마커 행으로 같이 저장 - Claude가 일시적으로
    실패해서 폴백이 캐시됐을 뿐인데 그걸 "정상 생성된 리포트"로 착각해 계속 재사용하는
    것을 막기 위함(9-8번 참고). strength/weakness 계열 항목은 {stat,title,detail}
    구조를 _encode_item으로 JSON 인코딩해 content에 저장한다."""
    db.query(Insight).filter(Insight.team_id == team_id, Insight.opponent_team_id.is_(None)).delete()

    now = _now_kst()
    rows = [Insight(team_id=team_id, target_type="team", insight_type="summary",
                     content=report["intro"], generated_at=now)]
    rows += [Insight(team_id=team_id, target_type="team", insight_type="strength",
                      content=_encode_item(s), generated_at=now) for s in report["strengths"]]
    rows += [Insight(team_id=team_id, target_type="team", insight_type="weakness",
                      content=_encode_item(w), generated_at=now) for w in report["weaknesses"]]
    rows.append(Insight(team_id=team_id, target_type="team", insight_type="strategy",
                         content=report["tactic"], generated_at=now))
    rows.append(Insight(team_id=team_id, target_type="team", insight_type="source",
                         content=source, generated_at=now))

    name_to_puuid = {p["name"]: p["id"] for p in roster}
    for fb in report["playerFeedback"]:
        puuid = name_to_puuid.get(fb["name"])
        if not puuid:
            continue
        rows.append(Insight(team_id=team_id, target_type="player", target_puuid=puuid,
                             insight_type="strength", content=_encode_item(fb["strength"]), generated_at=now))
        rows.append(Insight(team_id=team_id, target_type="player", target_puuid=puuid,
                             insight_type="weakness", content=_encode_item(fb["weakness"]), generated_at=now))

    db.add_all(rows)
    db.commit()


def _collect_team_context(db: Session, team: Team) -> dict:
    """3번 Step 1~2 - 다른 탭이 이미 계산해둔 결과만 모은다(재계산 없음)."""
    return {
        "stats": my_team_stats.build_my_team_stats(db, team),
        "analysis": my_team_analysis.build_my_team_analysis(db, team.team_id),
    }


async def _collect_roster_with_detail(db: Session, team: Team) -> tuple[list[dict], dict[str, dict]]:
    roster = await my_team_players.build_my_team_players(db, team)
    details = {
        p["id"]: my_team_player_detail.build_my_team_player_detail(db, team.team_id, p["id"])
        for p in roster
    }
    return roster, details


def _build_prompt(context: dict, roster: list[dict], details: dict[str, dict]) -> tuple[str, str]:
    """(system_prompt, user_prompt) - AI_리포트_개발_설계.md 4-2번.

    strengths/weaknesses/playerFeedback.strength/weakness는 {stat,title,detail}
    객체이고, detail은 개조식 구 1~2개짜리 문자열 배열이다(4차 변경 - 완결형 문장이
    딱딱하고 한 줄로 길게 나열되면 읽기 불편하다는 실사용 피드백 반영). 프론트는
    detail 배열의 각 원소를 별도 줄로 렌더링한다."""
    team_name = context["stats"].get("name") or "우리 팀"
    system_prompt = (
        "너는 발로란트 프리미어 팀 전술 분석가다. 아래 사용자 메시지에 주어진 통계만 "
        "근거로 한국어로 분석하고, 반드시 다음 JSON 스키마와 정확히 일치하는 JSON 객체 "
        "하나만 응답하라(스키마 밖 텍스트/설명/마크다운 금지):\n"
        "{\n"
        '  "intro": string,               // 팀 전반 요약 2~3문장\n'
        '  "strengths": [                 // 팀 강점 정확히 3개\n'
        '    {"stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        '  "weaknesses": [                // 팀 약점 정확히 3개, 형식 동일\n'
        '    {"stat": string, "title": string, "detail": string[]}\n'
        "  ],\n"
        '  "tactic": string,              // 전술 제안 1문단\n'
        '  "playerFeedback": [            // 아래 로스터 전원, 각 1개씩\n'
        "    {\n"
        '      "id": string,\n'
        '      "strength": {"stat": string, "title": string, "detail": string[]},\n'
        '      "weakness": {"stat": string, "title": string, "detail": string[]}\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "strengths/weaknesses의 각 항목과 playerFeedback의 strength/weakness는 반드시 "
        "stat/title/detail 세 필드로 나눠서 쓰고, 각각 아래 규칙을 지켜라:\n"
        "- stat: 근거가 되는 핵심 수치나 요약값 하나만, 5자 내외로 아주 짧게(예: "
        '"68%", "4개 맵 0승"). 여러 수치를 나열하지 마라.\n'
        "- title: 그 수치가 무엇에 대한 것인지 5~12자 내외 명사구만(예: \"선취킬 후 "
        '라운드 승리율\"). 숫자를 title에 넣지 마라.\n'
        "- detail: 정확히 1~2개의 짧은 구로 이루어진 문자열 배열. 각 구는 6~14자 "
        "내외이며 반드시 보고서식 개조식으로 끝내라 - 명사형이나 어간+'ㅁ/음'으로 "
        '끝내고("~부족", "~필요", "~시급", "~우수", "~흔들림"), "~다/~한다/~하다/'
        '~합니다"로 끝나는 완결형 문장은 절대 쓰지 마라. stat에 쓴 수치나 그와 동일한 '
        "의미의 표현(퍼센트, 비율, 배수, 순위 등 어떤 형태로든)을 detail 안에서 절대 "
        "다시 쓰지 마라 - stat과 detail은 서로 다른 정보를 담아야 한다(stat=얼마나, "
        "detail=왜/무슨 의미). 구가 2개면 원인→제안, 상황→결과처럼 자연스러운 의미 "
        "단위로 끊어라.\n"
        "나쁜 예(하지 마라): {\"stat\": \"70%\", \"title\": \"선취 실점 후 방어\", "
        '"detail": ["70%의 높은 패배율을 기록하여 수비 열세 상황 극복 능력이 부족하고 '
        '경기 후반부에 심화될 가능성이 크다"]} → 완결형 문장, 숫자 반복, 한 구가 너무 '
        "길다.\n"
        "좋은 예: {\"stat\": \"70%\", \"title\": \"선취 실점 후 방어\", \"detail\": "
        '["선취점 허용 시 급격히 흔들림", "수비 조직력 재정비 필요"]}\n'
        f"playerFeedback는 반드시 아래 로스터의 {len(roster)}명 전원에 대해, 나열된 id를 "
        "그대로 사용해 정확히 하나씩만 작성하라. "
        f'이 팀의 정식 이름은 "{team_name}"이다 - intro/tactic에서 팀을 가리킬 때는 '
        f'항상 이름 뒤에 "팀"을 붙여서 써라(예: "{team_name} 팀은 ...", "{team_name} '
        '팀의 ..." - 빈 괄호나 플레이스홀더 없이, "팀" 없이 이름만 쓰지도 말 것). '
        "title/detail은 명사구/개조식이라 팀 이름을 넣지 않아도 된다.\n"
        'intro/tactic 안에서 로스터의 특정 선수 이름을 언급할 때도 마찬가지로 이름 뒤에 '
        '"선수"를 붙여서 써라(예: "duk3 선수는 ...", "SacR1ficE 선수의 ..." - 이름만 '
        "단독으로 쓰지 말 것). playerFeedback은 name/role 필드가 이미 따로 있으니 그 "
        "안의 strength/weakness에서는 이름을 반복해서 부르지 않아도 된다.\n"
        "숫자 사용 규칙(stat 필드도 포함해 intro/title/detail/tactic 전부에 예외 없이 적용):\n"
        "- 절대 쓰면 안 되는 것: ACS, K/D나 KD 비율(예: \"1.05\", \"0.71\", \"5.0 KD\"), "
        "ADR, 킬/데스/어시스트 개수. 사용자 메시지에 [선수별 상세]로 준 JSON 안의 atkKd/"
        "defKd/ecoKd/pistolKd/weapons[].kd 같은 필드들도 전부 이 KD 비율에 해당하니 "
        "본문에 그 숫자를 그대로 절대 인용하지 마라 - 크고 작음(높다/낮다/우수하다/"
        "부족하다) 같은 정성적 서술로만 표현해라.\n"
        "- 써도 되는 것: 승률/성공률/헤드샷 비율처럼 %(퍼센트)로 표현되는 값과, 순수 "
        '개수 표현(예: "4개 맵", "0승")뿐이다.\n'
        "이 규칙을 지키는 이유: ACS/KD/ADR 같은 원본 수치는 이미 다른 탭(팀 분석/개인 "
        "분석)에 표로 나와 있어 여기서 또 반복할 필요가 없다."
    )

    roster_lines = "\n".join(
        f"- id={p['id']} 이름={p['name']} role={p.get('role')} ACS={p.get('acs')} "
        f"KD={p.get('kd')} HS%={p.get('hs')} ADR={p.get('adr')} 주요요원={p.get('mostAgent')}"
        for p in roster
    )
    user_prompt = (
        f"[팀 이름]\n{team_name}\n\n"
        f"[팀 최근 폼]\n{json.dumps(context['stats'].get('recentSummary'), ensure_ascii=False)}\n\n"
        f"[선수 랭킹(ACS 상위)]\n{json.dumps(context['stats'].get('playerRanking'), ensure_ascii=False)}\n\n"
        f"[맵별 승률]\n{json.dumps(context['stats'].get('mapWinrates'), ensure_ascii=False)}\n\n"
        f"[라운드 페이즈 통계(공격/수비/피스톨/에코 승률, 선취킬/선취死 이후 라운드 결과율)]\n"
        f"{json.dumps(context['analysis'].get('roundInfo'), ensure_ascii=False)}\n\n"
        f"[교전 통계(1대1/1대2 클러치 성공률, 듀얼리스트 매치업)]\n"
        f"{json.dumps(context['analysis'].get('engagementInfo'), ensure_ascii=False)}\n\n"
        f"[맵별 상세(선호 사이트, 조합, 강점/약점 선수 등)]\n"
        f"{json.dumps(context['analysis'].get('mapInfoByMap'), ensure_ascii=False)}\n\n"
        f"[로스터]\n{roster_lines}\n\n"
        f"[선수별 상세(맵별 지표, 조준, 클러치, 교전)]\n{json.dumps(details, ensure_ascii=False)}"
    )
    return system_prompt, user_prompt


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """Anthropic Messages API는 OpenAI의 response_format={"type":"json_object"}같은
    JSON 강제 모드가 없다 - 프롬프트로 "JSON만 응답하라"고 지시해도 가끔 ```json ... ```
    코드펜스로 감싸서 줄 수 있어(실사용 관찰) json.loads 전에 방어적으로 벗겨낸다."""
    return _CODE_FENCE_RE.sub("", text.strip()).strip()


def _call_claude(system_prompt: str, user_prompt: str) -> str | None:
    client = _get_client()
    if client is None:
        return None
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return _strip_code_fence(text)


def _validate_stat_item(item, label: str) -> dict:
    """strengths/weaknesses/playerFeedback.strength/weakness 공통 shape 검증.
    detail은 1~2개의 비어있지 않은 문자열로 이루어진 배열이어야 한다(4차 - 개조식
    구 배열)."""
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


def _parse_and_validate(raw_json: str, roster: list[dict]) -> dict:
    """2번 스키마와 일치하는지 확인 - 어긋나면 ValueError(호출부가 폴백으로 전환).
    strengths/weaknesses/playerFeedback.strength/weakness는 {stat,title,detail}
    구조를 각각 _validate_stat_item으로 검증한다."""
    data = json.loads(raw_json)

    if not isinstance(data.get("intro"), str) or not data["intro"].strip():
        raise ValueError("intro 누락/빈 값")
    if not isinstance(data.get("tactic"), str) or not data["tactic"].strip():
        raise ValueError("tactic 누락/빈 값")

    raw_strengths = data.get("strengths") or []
    raw_weaknesses = data.get("weaknesses") or []
    if len(raw_strengths) != 3:
        raise ValueError(f"strengths는 정확히 3개여야 함 (받음: {len(raw_strengths)}개)")
    if len(raw_weaknesses) != 3:
        raise ValueError(f"weaknesses는 정확히 3개여야 함 (받음: {len(raw_weaknesses)}개)")
    strengths = [_validate_stat_item(s, f"strengths[{i}]") for i, s in enumerate(raw_strengths)]
    weaknesses = [_validate_stat_item(w, f"weaknesses[{i}]") for i, w in enumerate(raw_weaknesses)]

    feedback_by_id = {f.get("id"): f for f in (data.get("playerFeedback") or [])}
    player_feedback = []
    for p in roster:
        fb = feedback_by_id.get(p["id"])
        if not fb:
            raise ValueError(f"playerFeedback에 로스터 id={p['id']}({p['name']}) 누락")
        strength = _validate_stat_item(fb.get("strength"), f"playerFeedback[{p['id']}].strength")
        weakness = _validate_stat_item(fb.get("weakness"), f"playerFeedback[{p['id']}].weakness")
        player_feedback.append({
            "name": p["name"],
            "role": p.get("role") or "-",
            "acs": p.get("acs", 0),
            "avatarUrl": p.get("avatarUrl"),
            "strength": strength,
            "weakness": weakness,
        })

    return {
        "intro": data["intro"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "tactic": data["tactic"],
        "playerFeedback": player_feedback,
    }


def _pct(value) -> str:
    return f"{value}%" if isinstance(value, (int, float)) else "정보 없음"


def _fallback_report(context: dict, roster: list[dict]) -> dict:
    """Claude 미설정/호출 실패/파싱 실패 시 결정론적 템플릿(6번 - 실제 숫자는 채우되
    문장은 규칙 기반으로 조립). ml/engagement_predictor.py의 heuristic-v0와 같은 철학.
    strengths/weaknesses/playerFeedback.strength/weakness도 Claude 경로와 동일하게
    {stat,title,detail(list)} shape과 개조식 톤으로 맞춘다 - 프론트가 source 무관하게
    같은 컴포넌트로 렌더링할 수 있어야 하기 때문."""
    stats = context["stats"]
    round_info = context["analysis"].get("roundInfo") or {}
    engagement = context["analysis"].get("engagementInfo") or {}
    recent = stats.get("recentSummary") or {}
    total_games = (recent.get("wins", 0) or 0) + (recent.get("losses", 0) or 0)

    team_label = f"{stats.get('name')} 팀" if stats.get("name") else "우리 팀"
    intro = (
        f"{team_label}은 최근 {total_games}경기 기준 "
        f"승률 {_pct(recent.get('winRate'))}를 기록 중입니다. "
        f"공격 승률 {_pct(round_info.get('atkWinRate'))}, 수비 승률 {_pct(round_info.get('defWinRate'))}입니다."
    )
    strengths = [
        {"stat": _pct(round_info.get('defWinRate')), "title": "수비 라운드 승률",
         "detail": ["수비 사이드 안정적 운영"]},
        {"stat": _pct(round_info.get('fbWinPct')), "title": "선취킬 후 마무리율",
         "detail": ["라운드 마무리 능력 우수"]},
        {"stat": _pct(engagement.get('trade1v1')), "title": "1대1 클러치 성공률",
         "detail": ["단독 교전 결정력 우수"]},
    ]
    weaknesses = [
        {"stat": _pct(round_info.get('ecoWinRate')), "title": "에코 라운드 승률",
         "detail": ["경제 열세 시 운영 미흡"]},
        {"stat": _pct(engagement.get('trade1v2')), "title": "1대2 클러치 성공률",
         "detail": ["다수 열세 교전 판단 부족"]},
        {"stat": _pct(round_info.get('fdLosePct')), "title": "선취 실점 후 패배율",
         "detail": ["실점 후 만회 능력 시급"]},
    ]
    tactic = (
        "AI 연동이 정상 동작하면 맵/사이드/조합까지 반영한 구체적인 전술 제안을 제공합니다. "
        "지금은 에코 라운드와 다수 열세 교전에서의 판단을 우선 점검해보는 것을 권장합니다."
    )
    player_feedback = [
        {
            "name": p["name"],
            "role": p.get("role") or "-",
            "acs": p.get("acs", 0),
            "avatarUrl": p.get("avatarUrl"),
            "strength": {
                "stat": _pct(p.get('hs')),
                "title": "헤드샷 비율",
                "detail": ["팀 내 준수한 조준 지표"],
            },
            "weakness": {
                "stat": "",
                "title": "개선점 분석 대기",
                "detail": ["AI 연동 정상화 후 제공 예정"],
            },
        }
        for p in roster
    ]
    return {"intro": intro, "strengths": strengths, "weaknesses": weaknesses, "tactic": tactic, "playerFeedback": player_feedback}


async def build_my_team_ai_report(db: Session, team: Team) -> dict:
    """진입점 - routers/my_team.py::GET /ai-report가 그대로 호출.

    1) 로스터를 먼저 확정(캐시 판독에도 필요 - name/role/acs/avatarUrl은 insights에
       안 남기고 매번 최신 값을 갖다 붙인다).
    2) 캐시(insights)가 있고 "실제 Claude가 생성한 것"이며 이 팀의 최신 매치보다
       새로 생성된 것이면 그대로 반환 - 폴백으로 저장됐던 캐시는 재사용하지 않고
       매번 Claude를 다시 시도한다(9-8번 - 크레딧 부족 등 일시적 실패로 폴백이
       캐시되면 문제가 나아진 뒤에도 계속 폴백만 보이는 문제 방지). 이 경로에서만
       API를 호출하므로, 캐시가 붙은 이후 조회는 항상 즉시 응답한다.
    3) 아니면 Claude로 새로 생성 → 실패하면 폴백 템플릿 → 어느 쪽이든 insights에
       source("claude"/"fallback")와 함께 저장."""
    context = _collect_team_context(db, team)
    roster, details = await _collect_roster_with_detail(db, team)

    cached, generated_at, cached_source = _read_cached_report(db, team.team_id, roster)
    latest_match_at = _latest_match_at(db, team.team_id)
    is_fresh = generated_at and (latest_match_at is None or generated_at >= latest_match_at)
    if cached and cached_source == "claude" and is_fresh:
        return cached

    system_prompt, user_prompt = _build_prompt(context, roster, details)
    report = None
    # LLM 응답은 확률적이라 가끔 로스터 중 한두 명이 playerFeedback에서 누락되는 등
    # 스키마를 못 맞출 때가 있다(실사용 관찰 - 같은 프롬프트를 재시도하면 보통 성공함).
    # 폴백으로 바로 넘어가기 전에 몇 번 더 시도한다.
    for attempt in range(CLAUDE_MAX_ATTEMPTS):
        try:
            raw = _call_claude(system_prompt, user_prompt)
            if raw is not None:
                report = _parse_and_validate(raw, roster)
            break
        except Exception as e:  # noqa: BLE001 - Claude 호출/JSON 파싱 등 다양한 실패를 전부 흡수
            print(f"[ai_report] Claude 생성 실패(시도 {attempt + 1}/{CLAUDE_MAX_ATTEMPTS}): {e}")

    source = "claude"
    if report is None:
        report = _fallback_report(context, roster)
        source = "fallback"

    _save_report(db, team.team_id, report, roster, source)
    return report