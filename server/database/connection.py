from pathlib import Path
from collections.abc import Generator
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# .env 경로 가져오기
BASE_DIR = Path(__file__).resolve().parents[1]

# fast-shoppy-server/.env 읽기
load_dotenv(BASE_DIR / ".env")

DB_USER=os.getenv("DB_USER")
DB_PASSWORD=os.getenv("DB_PASSWORD") 
DB_HOST=os.getenv("DB_HOST")
DB_PORT=os.getenv("DB_PORT")
DB_NAME=os.getenv("DB_NAME")

if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise RuntimeError("환경변수 파일의 (DB_USER, DB_PASSWORD, DB_NAME)를 확인하세요")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# Engine 생성
engine = create_engine(
    DATABASE_URL,
    echo = True,            # SQL 실행 로그 출력
    pool_pre_ping = True    # DB 연결 자동 체크
)

# Session Factory
SessionLocal = sessionmaker(
    bind = engine,
    autoflush = False,
    autocommit = False,
    expire_on_commit= False
)

# 모든 모델(DB연동)의 부모 클래스 정의
class Base(DeclarativeBase):
    pass


# Dependency
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
            yield db
    finally:
            db.close()