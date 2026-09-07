"""
회원가입 / 로그인 (SignupPage, LoginPage) + teams 계정 CRUD.

프론트 연동은 아직 signup/login만 붙어있고 GET·PATCH·DELETE /me는 프론트에서 아직
호출하는 곳이 없다(추후 마이페이지 등에서 주소만 연결하면 되도록 미리 구현해둔 것).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from models.team import Team
from services import auth as auth_service
from services import henrik_api

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer_scheme = HTTPBearer(auto_error=False)


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


class TeamOut(BaseModel):
    teamId: str
    email: str
    loginId: str
    teamName: str
    teamTag: str
    teamImage: str | None = None
    division: str | None = None
    rankingPoints: int
    verified: bool
    verifiedAt: datetime | None = None
    createdAt: datetime

    @staticmethod
    def from_team(team: Team) -> "TeamOut":
        return TeamOut(
            teamId=team.team_id,
            email=team.email,
            loginId=team.login_id,
            teamName=team.team_name,
            teamTag=team.team_tag,
            teamImage=team.team_image,
            division=team.division,
            rankingPoints=team.ranking_points,
            verified=team.verified,
            verifiedAt=team.verified_at,
            createdAt=team.created_at,
        )


class UpdateTeamRequest(BaseModel):
    # 전부 optional - 보낸 필드만 반영(부분 업데이트). team_name/team_tag/team_id는
    # Henrik 프리미어 팀 자체를 바꾸는 것과 같아서(가입 시에만 결정) 여기서는 다루지 않는다.
    email: str | None = None
    currentPassword: str | None = None
    newPassword: str | None = None


class DeleteTeamRequest(BaseModel):
    password: str


def get_current_team(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Team:
    """Authorization: Bearer <JWT> 헤더로 로그인 팀을 식별. httpClient.js가 로그인 후
    이미 이 헤더를 붙여서 보내고 있었지만(localStorage의 valo_auth_token), 지금까지는
    서버 쪽에 이걸 검증하는 엔드포인트가 하나도 없었다."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    payload = auth_service.decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")
    team = auth_service.find_team_by_id(db, payload.get("sub"))
    if team is None:
        raise HTTPException(status_code=401, detail="존재하지 않는 계정입니다.")
    return team


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

    customization = team_info.get("customization") or {}
    placement = team_info.get("placement") or {}
    team_image = customization.get("image")
    division = placement.get("division")

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
            division=str(division) if division is not None else None,
            ranking_points=placement.get("points") or 0,
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


@router.get("/me", response_model=TeamOut)
def get_me(current: Team = Depends(get_current_team)):
    """로그인한 팀 계정 조회(Read). teams 행 전체를 그대로 내려준다."""
    return TeamOut.from_team(current)


@router.patch("/me", response_model=TeamOut)
def update_me(
    payload: UpdateTeamRequest,
    current: Team = Depends(get_current_team),
    db: Session = Depends(get_db),
):
    """로그인한 팀 계정 부분 수정(Update). email과 비밀번호만 대상 - 비밀번호를 바꾸려면
    currentPassword가 실제 비밀번호와 일치해야 한다."""
    fields: dict = {}
    if payload.email:
        fields["email"] = payload.email
    if payload.newPassword:
        if not payload.currentPassword or not auth_service.verify_password(
            payload.currentPassword, current.password_hash
        ):
            raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
        fields["password_hash"] = auth_service.hash_password(payload.newPassword)

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 값이 없습니다.")

    try:
        updated = auth_service.update_team(db, current, **fields)
    except auth_service.DuplicateTeamError:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    return TeamOut.from_team(updated)


@router.delete("/me")
def delete_me(
    payload: DeleteTeamRequest,
    current: Team = Depends(get_current_team),
    db: Session = Depends(get_db),
):
    """로그인한 팀 계정 삭제(Delete, 회원 탈퇴). 되돌릴 수 없는 작업이라 비밀번호 재확인을
    받는다."""
    if not auth_service.verify_password(payload.password, current.password_hash):
        raise HTTPException(status_code=400, detail="비밀번호가 올바르지 않습니다.")
    auth_service.delete_team(db, current)
    return {"success": True}
