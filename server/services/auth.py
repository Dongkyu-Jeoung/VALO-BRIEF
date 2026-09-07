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
    team_id: str,
    email: str,
    login_id: str,
    password: str,
    privacy_agreed: bool,
    team_name: str,
    team_tag: str,
    team_image: str | None = None,
) -> Team:
    """team_id/team_image는 더 이상 여기서 생성하지 않는다 - team_id는 더 이상
    AUTO_INCREMENT가 아니라 Henrik 프리미어 팀 API(get_premier_team)가 돌려주는 실제
    premier team id를 그대로 쓰고, team_image도 같은 응답의 customization.image다.
    호출부(routers/auth.py)가 Henrik 조회를 먼저 마치고 그 결과를 넘겨준다 - 즉 이
    team_name/team_tag가 실제 존재하는 프리미어 팀이어야만 가입이 된다."""
    team = Team(
        team_id=team_id,
        email=email,
        login_id=login_id,
        password_hash=hash_password(password),
        privacy_agreed=privacy_agreed,
        team_name=team_name,
        team_tag=team_tag,
        team_image=team_image,
    )
    db.add(team)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateTeamError from exc
    db.refresh(team)
    return team
