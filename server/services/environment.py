"""실행 디렉터리와 무관하게 프로젝트 환경 설정을 읽는다."""
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_environment(project_root=PROJECT_ROOT):
    # 명시적인 프로세스 환경변수 > 최상위 .env > 기존 server/.env.
    # DB 모듈도 같은 순서로 읽어 import 순서에 따라 키가 달라지지 않게 한다.
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(project_root / "server" / ".env", override=False)
