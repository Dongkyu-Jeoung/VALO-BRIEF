import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers.search import router as search_router
from routers.players import router as players_router
from routers.teams import router as teams_router
from routers.auth import router as auth_router
from routers.predict import router as predict_router
from routers.my_team import router as my_team_router
from services import henrik_api, valorant_api

app = FastAPI()


@app.on_event("startup")
async def _warm_henrik_client():
    await henrik_api.warm_up()


# 전역 예외 핸들러: Henrik 레이트리밋(429)에 걸리면 henrik_api.HenrikRateLimitError가
# 라우터까지 그대로 올라온다 - 이걸 그냥 500으로 두면 프론트가 "검색 중 오류가
# 발생했습니다"로만 뭉뚱그리게 되는데, 실제로는 "존재하지 않음"이 아니라 "지금은 너무 많이
# 요청해서 잠시 후 다시 하면 된다"는 명확히 다른 상황이라 503 + 안내 메시지로 구분해준다
# (검색/팀·선수 프로필 라우터 전부 이 예외를 던질 수 있어 라우터마다 따로 잡지 않고 여기
# 한 곳에서 처리).
@app.exception_handler(henrik_api.HenrikRateLimitError)
async def _handle_henrik_rate_limit(request: Request, exc: henrik_api.HenrikRateLimitError):
    return JSONResponse(
        status_code=503,
        content={"detail": "요청이 많아 잠시 조회할 수 없습니다. 몇 초 후 다시 시도해 주세요."},
    )


@app.on_event("shutdown")
async def _close_henrik_client():
    await henrik_api.aclose_client()
    await valorant_api.aclose_client()

# CORSMiddleware 추가
origins = os.getenv(
    "FRONT_ORIGINS","http://localhost:3000,http://localhost:5173" 
    ).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"]
)

# 개인 검색 or 팀 검색 Header/Main
app.include_router(search_router)

# 개인 검색 (Frame 04) - 선수 프로필
app.include_router(players_router)

# 팀 검색 - 팀 프로필 상세 페이지
app.include_router(teams_router)
# 회원가입 / 로그인
app.include_router(auth_router)

# 승률 예측 모델 연결
app.include_router(predict_router)

# 우리팀 분석 (로그인 필요, DB 캐시 기반)
app.include_router(my_team_router)