import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.search import router as search_router
from routers.players import router as players_router
from services import henrik_api

app = FastAPI()


@app.on_event("shutdown")
async def _close_henrik_client():
    await henrik_api.aclose_client()

# CORSMiddleware 추가
origins = os.getenv(
    "FRONT_ORIGINS","http://localhost:3000,http://localhost:5173" 
    ).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"]
)

# 개인 검색 or 팀 검색 Header/Main
app.include_router(search_router)

# 개인 검색 (Frame 04) - 선수 프로필
app.include_router(players_router)