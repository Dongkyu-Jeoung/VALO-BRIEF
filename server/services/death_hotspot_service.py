# server/services/death_hotspot_service.py
# 팀+맵 기준으로 선수별 최다 사망 위치(핫스팟)를 계산.
#
# models/death_event.py(DeathEvent)·schema/death_event.py(DeathHotspot)가 원래 이
# 기능을 위해 설계됐지만, DeathEvent를 실제로 저장하는 코드가 프로젝트 어디에도 없어
# get_death_hotspots(DB 조회 경로)는 아직 미구현 상태다(2026-09-11 확인). 대신
# services/team_profile.py·services/my_team_analysis.py가 이미 정규화(0~100)까지 끝낸
# 원본 사망 좌표 리스트를 그 자리에서 이 모듈의 compute_player_hotspots로 넘겨 집계한다
# - 화면(팀원 사망 위치 분석)에 필요한 "선수 1명당 대표 위치 1개"를 이 방식으로 만든다.

# 0~100 정규화 좌표계 기준 격자 한 칸 크기. 이 값을 줄이면 칸이 잘게 쪼개져 핫스팟이
# 더 정밀해지지만 표본이 적은 맵에서는 칸마다 표본이 1개씩만 흩어져 대표성이 떨어질 수
# 있다 - 필요시 조정.
GRID_SIZE = 5


def compute_player_hotspots(points: list[dict]) -> list[dict]:
    """points: [{"x": 0~100, "y": 0~100, "puuid": str}, ...] (여러 매치를 합친 원본
    사망 좌표 리스트, services/team_profile.py::_death_locations·services/
    my_team_analysis.py::_death_locations_for_match가 만든다).

    선수(puuid)별로:
      1. 좌표를 GRID_SIZE 단위 격자 칸으로 비닝
      2. 칸별로 몇 번 죽었는지 카운트
      3. 가장 많이 죽은 칸을 찾아, 그 칸에 속한 좌표들의 평균을 대표 위치로 삼음
    한 선수당 항목 1개만 반환한다 - 팀 로스터가 5명이면 결과도 최대 5개.
    playerName은 여기서 채우지 않는다(이 함수는 좌표만 알고 이름은 모름) - 호출부가
    이미 갖고 있는 puuid->이름 조회로 결과에 덧붙여야 한다."""
    by_player: dict[str, dict[tuple[int, int], list[tuple[float, float]]]] = {}
    for p in points:
        puuid = p.get("puuid")
        x, y = p.get("x"), p.get("y")
        if not puuid or x is None or y is None:
            continue
        cells = by_player.setdefault(puuid, {})
        cell_key = (round(x / GRID_SIZE), round(y / GRID_SIZE))
        cells.setdefault(cell_key, []).append((x, y))

    hotspots = []
    for puuid, cells in by_player.items():
        best_cell_points = max(cells.values(), key=len)
        avg_x = round(sum(pt[0] for pt in best_cell_points) / len(best_cell_points), 2)
        avg_y = round(sum(pt[1] for pt in best_cell_points) / len(best_cell_points), 2)
        hotspots.append({
            "playerId": puuid,
            "x": avg_x,
            "y": avg_y,
            "deathCount": len(best_cell_points),
        })
    return hotspots


def get_death_hotspots(team_id: str, map_id: str):
    # DB(death_event 테이블) 기반 조회 경로 - DeathEvent를 실제로 저장하는 파이프라인이
    # 생기면 여기서 구현. 지금은 team_profile.py/my_team_analysis.py가 raw match
    # 데이터로 compute_player_hotspots를 직접 호출하는 경로만 쓰인다.
    pass