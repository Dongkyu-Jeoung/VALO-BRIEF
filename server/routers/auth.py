"""
회원가입 / 로그인 (SignupPage, LoginPage).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    # 형식 검증은 프론트에서 이미 수행 (email-validator 의존성 추가를 피하기 위해 str로 수신)
    email: str
    id: str
    password: str
    agree: bool
    teamName: str
    teamTag: str


class LoginRequest(BaseModel):
    id: str
    password: str


class RiotVerifyRequest(BaseModel):
    teamName: str
    teamTag: str


@router.post("/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    if not payload.agree:
        raise HTTPException(status_code=400, detail="개인정보 수집·이용에 동의해야 합니다.")

    try:
        auth_service.create_team(
            db,
            email=payload.email,
            login_id=payload.id,
            password=payload.password,
            privacy_agreed=payload.agree,
            team_name=payload.teamName,
            team_tag=payload.teamTag,
        )
    except auth_service.DuplicateTeamError:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일, 아이디 또는 팀 정보입니다.")

    return {"success": True}


@router.post("/riot-verify")
def riot_verify(payload: RiotVerifyRequest):
    # TODO: 실제 Riot 계정 연동/인증 붙기 전까지의 임시 스텁 - 항상 성공 처리해서
    # 회원가입 플로우가 막히지 않게 한다 (QA용으로 teamTag='FAIL'만 실패 재현).
    return {"verified": payload.teamTag.upper() != "FAIL"}


@router.get("/id-available")
def check_id_available(id: str, db: Session = Depends(get_db)):
    team = auth_service.find_team_by_login_id(db, id)
    return {"available": team is None}


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    team = auth_service.find_team_by_login_id(db, payload.id)
    if not team or not auth_service.verify_password(payload.password, team.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    token = auth_service.create_access_token(team)
    return {
        "token": token,
        "user": {
            "id": team.team_id,
            "loginId": team.login_id,
            "teamName": team.team_name,
            "teamTag": team.team_tag,
            "nickname": team.team_name,
        },
    }
