"""
회원가입 / 로그인 (SignupPage, LoginPage).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from services import auth as auth_service
from services import henrik_api

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
async def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    if not payload.agree:
        raise HTTPException(status_code=400, detail="개인정보 수집·이용에 동의해야 합니다.")

    # team_id는 더 이상 내부에서 생성하지 않고 Henrik 프리미어 팀의 실제 id를 그대로
    # 쓴다 - team_name/team_tag가 실제 존재하는 프리미어 팀이어야만 가입이 된다
    # (팀 대표 개인 계정 대신 team_name/team_tag 기준으로 인증하기로 한 결정).
    team_info = await henrik_api.get_premier_team(payload.teamName, payload.teamTag)
    if team_info is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 프리미어 팀입니다. 팀 이름/태그를 확인해 주세요.")

    team_image = (team_info.get("customization") or {}).get("image")

    try:
        auth_service.create_team(
            db,
            team_id=team_info["id"],
            email=payload.email,
            login_id=payload.id,
            password=payload.password,
            privacy_agreed=payload.agree,
            team_name=payload.teamName,
            team_tag=payload.teamTag,
            team_image=team_image,
        )
    except auth_service.DuplicateTeamError:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일, 아이디 또는 팀 정보입니다.")

    return {"success": True}


@router.post("/riot-verify")
async def riot_verify(payload: RiotVerifyRequest):
    """team_name/team_tag가 실제 Henrik 프리미어 팀인지 확인 (개인 Riot 계정 인증 아님 -
    팀 대표를 지정하기 어려워서 팀 이름/태그 기준으로만 인증하기로 함)."""
    team_info = await henrik_api.get_premier_team(payload.teamName, payload.teamTag)
    return {"verified": team_info is not None}


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
