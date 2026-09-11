"""
Claude(Anthropic API) 호출 공통 유틸 - "우리팀 분석 > AI 리포트"(services/ai_report.py)와
"상대팀 AI 인사이트"(services/opponent_ai_report.py) 둘 다 같은 클라이언트 설정/재시도
로직을 쓰므로 여기로 뺐다.

ANTHROPIC_API_KEY가 없으면 get_client()가 None을 반환하고, 호출부는 이를 "아직 학습/
설정 전"인 정상 상태로 다뤄 결정론적 템플릿으로 대체해야 한다(각 모듈의 폴백 로직 참고).
"""
import os
import re

from anthropic import Anthropic

from services.environment import load_environment

load_environment()

# 미정 사항 - 비용/응답 품질을 보고 조정 가능하도록 상수로 분리. gpt-4o-mini와 비슷한
# 비용/속도대의 모델 - 품질을 더 원하면 claude-sonnet-5로 교체.
MODEL_NAME = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
# LLM 응답이 스키마를 못 맞추면(항목 일부 누락 등, 실사용 관찰) 폴백 전에 재시도할 횟수.
MAX_ATTEMPTS = 3

# ml/engagement_predictor.py와 동일한 지연 로드 패턴 - 모듈 임포트 시점에 클라이언트를
# 만들면 키가 없는 환경(로컬 개발 등)에서 서버 전체가 못 뜬다.
_client = None
_client_loaded = False


def get_client():
    global _client, _client_loaded
    if not _client_loaded:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        _client = Anthropic(api_key=api_key) if api_key else None
        _client_loaded = True
    return _client


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def strip_code_fence(text: str) -> str:
    """Anthropic Messages API는 OpenAI의 response_format={"type":"json_object"}같은
    JSON 강제 모드가 없다 - 프롬프트로 "JSON만 응답하라"고 지시해도 가끔 ```json ... ```
    코드펜스로 감싸서 줄 수 있어(실사용 관찰) json.loads 전에 방어적으로 벗겨낸다."""
    return _CODE_FENCE_RE.sub("", text.strip()).strip()


def call_claude(system_prompt: str, user_prompt: str, *, max_tokens: int = MAX_TOKENS) -> str | None:
    """클라이언트가 없으면(키 미설정) None. 있으면 응답 텍스트(코드펜스 제거됨)를 반환."""
    client = get_client()
    if client is None:
        return None
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return strip_code_fence(text)


def generate_with_retry(system_prompt: str, user_prompt: str, parse_fn, *, log_prefix: str, max_attempts: int = MAX_ATTEMPTS):
    """call_claude -> parse_fn(raw_json_str)을 최대 max_attempts번 시도한다. parse_fn은
    검증까지 마친 dict를 반환하거나 스키마가 안 맞으면 예외(주로 ValueError)를 던져야
    한다 - 실패하면 다음 시도로 넘어간다(LLM 응답은 확률적이라 같은 프롬프트를 재시도하면
    보통 성공함, 실사용 관찰). 키 자체가 없으면(call_claude가 None) 재시도 없이 바로
    None. 전부 실패하면 None - 호출부가 결정론적 폴백으로 넘어가야 한다."""
    for attempt in range(max_attempts):
        try:
            raw = call_claude(system_prompt, user_prompt)
            if raw is None:
                return None
            return parse_fn(raw)
        except Exception as e:  # noqa: BLE001 - Claude 호출/JSON 파싱 등 다양한 실패를 전부 흡수
            print(f"[{log_prefix}] Claude 생성 실패(시도 {attempt + 1}/{max_attempts}): {e}")
    return None
