# server/models/death_event.py
# 사망 위치 원본 데이터 테이블

class DeathEvent:
    """
    한 번의 사망 기록 (라운드당 최대 5명 x 팀 x 라운드 수만큼 쌓임)
    """
    id: int
    match_id: str        # match.py의 Match와 연결
    team_id: str          # team.py의 Team과 연결
    player_id: str
    map_id: str           # 예: 'lotus'
    x: float              # 0~100 정규화된 좌표
    y: float
    round_num: int
    created_at: str