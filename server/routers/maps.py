"""
맵 메타데이터(미니맵 이미지 URL) 조회용 라우터.

프론트 gameData.js는 원래 로컬 이미지(src/assets/images/minimaps/*.png)를 썼는데,
services/map_coords_service.py의 좌표 변환 계수는 valorant-api.com의 공식 이미지를
기준으로 보정된 값이라, 로컬 이미지가 그 공식 이미지와 다른 버전(구도/크롭)이면
좌표 계산은 맞아도 화면에서는 엉뚱한 위치에 찍히는 문제가 있었다(2026-09-11, 스플릿
맵에서 실측 확인). 이 엔드포인트로 좌표 계산과 항상 같은 소스의 이미지 URL을 내려줘서
구조적으로 불일치가 안 생기게 한다.

프론트는 이 URL을 우선 쓰고, 요청 실패 시 기존 로컬 이미지로 폴백한다
(front/src/hooks/useMinimapUrls.js 참고) - 이 라우터가 죽어도 화면이 완전히 깨지지
않도록 하기 위함.
"""
from fastapi import APIRouter

from services.map_coords_service import get_map_minimaps

router = APIRouter(prefix="/api/maps", tags=["maps"])


@router.get("/minimaps")
def get_minimaps():
    """{"ascent": "https://media.valorant-api.com/.../displayicon.png", ...} 형태로
    반환. 서버 프로세스당 valorant-api.com 호출은 최초 1회뿐 - map_coords_service의
    캐시(_ensure_loaded)를 그대로 재사용하므로 이 엔드포인트를 몇 번을 호출해도 추가
    외부 호출은 없다."""
    return get_map_minimaps()