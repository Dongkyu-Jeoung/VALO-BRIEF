# server/services/death_hotspot_service.py
# 팀+맵 기준으로 선수별 최다 사망 위치(핫스팟)를 계산

def get_death_hotspots(team_id: str, map_id: str):
    # 1. death_event 테이블에서 team_id + map_id 조건으로 조회
    # 2. player_id별로 그룹화
    # 3. 좌표를 격자 단위로 비닝해서 카운트
    # 4. 선수별 최다 칸의 좌표 반환
    pass