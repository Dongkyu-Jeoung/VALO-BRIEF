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


def decode_access_token(token: str) -> dict | None:
    """create_access_token()이 발급한 JWT를 검증/디코드. 만료·서명 불일치 등은 전부
    None으로 통일해서 반환(호출부가 401로 변환) - 실패 사유별 분기는 필요 없음."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def find_team_by_login_id(db: Session, login_id: str) -> Team | None:
    return db.query(Team).filter(Team.login_id == login_id).first()


def find_team_by_id(db: Session, team_id: str) -> Team | None:
    return db.query(Team).filter(Team.team_id == team_id).first()


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
    division: str | None = None,
    ranking_points: int = 0,
) -> Team:
    """team_id/team_image/division/ranking_points는 더 이상 여기서 생성하지 않는다 -
    team_id는 더 이상 AUTO_INCREMENT가 아니라 Henrik 프리미어 팀 API(get_premier_team)가
    돌려주는 실제 premier team id를 그대로 쓰고, team_image/division/ranking_points도
    같은 응답의 customization.image/placement.division/placement.points다.
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
        division=division,
        ranking_points=ranking_points,
    )
    db.add(team)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateTeamError from exc
    db.refresh(team)
    return team


def update_team(db: Session, team: Team, **fields) -> Team:
    """전달된 컬럼만 부분 업데이트(비밀번호는 호출부가 이미 hash_password()로 해시해서
    password_hash로 넘긴다 - 여기서는 평문을 다루지 않음). email/team_name+team_tag
    유니크 제약을 건드리면 create_team()과 동일하게 DuplicateTeamError로 통일."""
    for key, value in fields.items():
        setattr(team, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateTeamError from exc
    db.refresh(team)
    return team


def delete_team(db: Session, team: Team) -> None:
    db.delete(team)
    db.commit()
