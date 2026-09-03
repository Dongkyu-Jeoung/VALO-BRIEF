"""
회원가입 / 로그인 - 비밀번호 해시·검증, JWT 발급, teams 테이블 접근. routers/auth.py 공용.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.team import Team

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


class DuplicateTeamError(Exception):
    """email/login_id/team_name+team_tag 중복 가입 시도."""


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_access_token(team: Team) -> str:
    payload = {
        "sub": str(team.team_id),
        "login_id": team.login_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def find_team_by_login_id(db: Session, login_id: str) -> Team | None:
    return db.query(Team).filter(Team.login_id == login_id).first()


def create_team(
    db: Session,
    *,
    email: str,
    login_id: str,
    password: str,
    privacy_agreed: bool,
    team_name: str,
    team_tag: str,
) -> Team:
    """프론트에서 받은 정보만 채워서 insert하고, 나머지 컬럼(premier_team_id/tier_id/
    season/conference/division/ranking_points)은 DB 기본값(NULL 또는 0)을 그대로 둔다."""
    team = Team(
        email=email,
        login_id=login_id,
        password_hash=hash_password(password),
        privacy_agreed=privacy_agreed,
        team_name=team_name,
        team_tag=team_tag,
    )
    db.add(team)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateTeamError from exc
    db.refresh(team)
    return team
