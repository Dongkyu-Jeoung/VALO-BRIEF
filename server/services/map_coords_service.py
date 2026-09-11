"""
Henrik(v2/match)의 게임 월드 좌표(x, y)를 미니맵 위에 찍을 수 있는 0~100 정규화 좌표로
변환한다 - 팀원 사망 위치 분석(히트맵) 섹션용(services/team_profile.py::_death_locations,
services/my_team_analysis.py::_death_locations_for_match이 이 모듈을 씀).

변환 계수(xMultiplier/yMultiplier/xScalarToAdd/yScalarToAdd)는 맵마다 다르고 Henrik/Riot
공식 API가 내려주지 않는다. 직접 하드코딩하면 라이엇이 맵을 리워크해서 좌표계가 바뀔 때
조용히 틀린 값을 쓰게 될 위험이 있어(models/death_event.py가 원래 기대하던 "0~100
정규화 좌표"를 안전하게 만들 방법이 없었음), 커뮤니티에서 널리 쓰이는 공개 API인
valorant-api.com/v1/maps에서 서버가 직접 받아와 캐싱하는 방식을 쓴다(2026-09-11,
이 서버 환경에서 해당 도메인으로의 네트워크 호출 가능 여부 직접 확인 완료).

캐시는 두 키로 동시에 만든다 - 소비처마다 갖고 있는 맵 식별자가 다르기 때문:
  - by_uuid: services/my_team_analysis.py는 DB(matches.map_uuid, ref_maps.uuid 출처)만
    갖고 있어 영문 맵 이름이 없다.
  - by_name: services/team_profile.py는 Henrik raw 응답(metadata.map, 영문명)을 그
    자리에서 가공하므로 uuid가 없다.

valorant-api.com 호출이 실패해도(네트워크 장애 등) 예외를 위로 던지지 않고 캐시를 빈
상태로 유지한다 - 이 모듈은 화면의 부가 정보(히트맵)만 담당하므로, 실패 시
normalize_location이 None을 반환해 호출부가 그 매치의 좌표만 조용히 스킵하게 한다
(화면 전체 응답이 깨지면 안 됨).
"""
import requests

_MAPS_API_URL = "https://valorant-api.com/v1/maps"
_REQUEST_TIMEOUT = 5

_coords_by_uuid: dict[str, dict] | None = None
_coords_by_name: dict[str, dict] | None = None


def _ensure_loaded() -> None:
    """모듈 최초 사용 시 한 번만 valorant-api.com을 호출해 두 캐시를 채운다(이후 호출은
    캐시만 읽음) - services/match_history.py의 _load_map_uuid_by_name과 동일한
    "참조 데이터 전역 캐시" 패턴."""
    global _coords_by_uuid, _coords_by_name
    if _coords_by_uuid is not None:
        return

    _coords_by_uuid = {}
    _coords_by_name = {}
    try:
        resp = requests.get(_MAPS_API_URL, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        maps_data = resp.json().get("data") or []
        for m in maps_data:
            coeffs = {
                "xMultiplier": m.get("xMultiplier"),
                "yMultiplier": m.get("yMultiplier"),
                "xScalarToAdd": m.get("xScalarToAdd"),
                "yScalarToAdd": m.get("yScalarToAdd"),
            }
            if any(v is None for v in coeffs.values()):
                continue  # 이 맵은 계수가 불완전 - 방어적으로 스킵(예: 로테이션 삭제된 구맵)

            uuid = str(m.get("uuid") or "").lower()
            name = str(m.get("displayName") or "").lower()
            if uuid:
                _coords_by_uuid[uuid] = coeffs
            if name:
                _coords_by_name[name] = coeffs
    except Exception as e:
        # 실패해도 조용히 넘어간다 - 캐시는 빈 dict로 남고, 이후 normalize_location이
        # 전부 None을 반환해 호출부가 히트맵 데이터 없이 나머지 응답은 정상 진행한다.
        print(f"[map_coords_service] valorant-api.com 맵 좌표 로드 실패: {e}")


def normalize_location(
    x: float, y: float, *, map_uuid: str | None = None, map_name_en: str | None = None
) -> dict | None:
    """게임 월드 좌표(x, y)를 미니맵 기준 0~100 정규화 좌표로 변환.
    map_uuid/map_name_en 중 최소 하나는 있어야 하며, map_uuid를 우선 시도하고 없으면
    map_name_en으로 찾는다. 계수를 못 찾으면(둘 다 없음, 혹은 valorant-api.com이 아직
    모르는 신규/구버전 맵 이름) None을 반환 - 호출부는 그 좌표를 조용히 버려야 한다."""
    _ensure_loaded()

    coeffs = None
    if map_uuid:
        coeffs = _coords_by_uuid.get(map_uuid.lower())
    if coeffs is None and map_name_en:
        coeffs = _coords_by_name.get(map_name_en.lower())
    if coeffs is None:
        return None

    nx = x * coeffs["xMultiplier"] + coeffs["xScalarToAdd"]
    ny = y * coeffs["yMultiplier"] + coeffs["yScalarToAdd"]
    return {"x": round(nx * 100, 2), "y": round(ny * 100, 2)}