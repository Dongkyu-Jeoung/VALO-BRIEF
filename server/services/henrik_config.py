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
    general = HenrikClientConfig("general", general_key, RateLimiter(58))
    # 추가 키 미등록/동일 키 등록 시 한 키의 예산을 두 번 할당하지 않는다.
    ml = (HenrikClientConfig("ml", ml_key, RateLimiter(43))
          if ml_key and ml_key != general_key else general)
    return general, ml


load_environment()
GENERAL, ML = build_client_configs(os.getenv("HENRIK_API_KEY"), os.getenv("HENRIK_ML_API_KEY"))
if ML is GENERAL:
    logging.getLogger(__name__).warning(
        "[HENRIK CONFIG] ML uses general key/budget; set a distinct HENRIK_ML_API_KEY for dual-key mode")
