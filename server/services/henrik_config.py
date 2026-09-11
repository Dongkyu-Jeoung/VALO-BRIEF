"""Henrik 키와 해당 키의 요청 예산을 한 객체로 묶는다."""
import logging
import os
from dataclasses import dataclass, field

from services.environment import load_environment
from services.rate_limiter import RateLimiter


@dataclass(frozen=True)
class HenrikClientConfig:
    name: str
    api_key: str | None = field(repr=False)
    limiter: RateLimiter = field(repr=False)

    @property
    def headers(self):
        return {"Authorization": self.api_key} if self.api_key else {}


def build_client_configs(general_key, ml_key):
    general_key = (general_key or "").strip() or None
    ml_key = (ml_key or "").strip() or None
    general = HenrikClientConfig("general", general_key, RateLimiter(43))
    # 추가 키 미등록/동일 키 등록 시 한 키의 예산을 두 번 할당하지 않는다.
    ml = (HenrikClientConfig("ml", ml_key, RateLimiter(58))
          if ml_key and ml_key != general_key else general)
    return general, ml


load_environment()
# 2026-09-11: 실제 Henrik 응답 헤더로 두 키의 진짜 한도를 확인한 결과(x-ratelimit-limit),
# HENRIK_API_KEY=60/분, HENRIK_ML_API_KEY=45/분이었다. 승부예측 한 건이 상대팀 선수
# 5명 분량을 순간적으로 최대 30건까지 몰아 부르는 반면(ml/valorant_git.py), 검색/화면
# 쪽은 여러 요청에 걸쳐 나눠 걸리는 편이라 순간 버스트에 더 취약한 예측 쪽에 한도가 더
# 큰 키를 배정한다 - 인자 순서를 바꿔서 GENERAL(검색/화면)이 원래 ML 몫이던 키를,
# ML(승부예측)이 원래 GENERAL 몫이던 키를 쓰게 한다. 두 예산은 여전히 완전히 분리돼
# 있음(서로 침범 안 함) - 어느 쪽에 어느 키를 주느냐만 바꾼 것.
GENERAL, ML = build_client_configs(os.getenv("HENRIK_ML_API_KEY"), os.getenv("HENRIK_API_KEY"))
if ML is GENERAL:
    logging.getLogger(__name__).warning(
        "[HENRIK CONFIG] ML uses general key/budget; set a distinct HENRIK_ML_API_KEY for dual-key mode")
