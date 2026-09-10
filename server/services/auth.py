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

# 리프레시 토큰: 탭을 켜놓은 동안은 로그인이 끊기지 않게 하려고 도입 - 실제 세션 경계는
# 프론트가 sessionStorage에 저장해서 탭을 닫으면 사라지는 것으로 강제하므로, 이 값 자체는
# "그 안에서 한 번도 안 껐을 때 최대 얼마나 버티게 할지"만 정하면 된다(넉넉하게 7일 기본값).
JWT_REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", str(60 * 24 * 7)))


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
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(team: Team) -> str:
    """access token보다 훨씬 수명이 긴 토큰. "type": "refresh"로 구분해서 access token
    검증 경로(get_current_team)에 잘못 흘러들어도 즉시 거부되게 한다. DB에 저장하지
    않는 stateless JWT라 서버 쪽에서 강제로 무효화(로그아웃 시 폐기)할 수는 없다 -
    탈취되면 자기 만료 시각까지는 계속 유효함에 유의."""
    payload = {
        "sub": str(team.team_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_REFRESH_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_token(token: str, expected_type: str) -> dict | None:
    """만료·서명 불일치·타입 불일치 등은 전부 None으로 통일해서 반환(호출부가 401로
    변환) - 실패 사유별 분기는 필요 없음."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def decode_access_token(token: str) -> dict | None:
    """create_access_token()이 발급한 JWT를 검증/디코드."""
    return _decode_token(token, "access")


def decode_refresh_token(token: str) -> dict | None:
    """create_refresh_token()이 발급한 JWT를 검증/디코드."""
    return _decode_token(token, "refresh")


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
