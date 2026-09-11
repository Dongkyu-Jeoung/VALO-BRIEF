"""
Henrik v2/match의 라운드 원본 배열(rounds - matches.round_detail_json과 완전히 같은
형태, services/match_history.py::upsert_match_history가 `match.get("rounds")`를
그대로 저장한 것)로부터 공격/수비/피스톨/에코 라운드 승률 등을 계산하는 순수 함수 모음.

2026-09-11: 원래 services/my_team_analysis.py 안에 private 함수로만 있었다("우리팀
분석" 탭이 DB 캐시(Match.round_detail_json + MatchPlayerStat, team_id로 필터)에서만
썼음). 상대팀(가입 여부 무관) AI 리포트를 만들려는데 상대는 team_id가 없어(FK 제약상
미가입 팀은 채울 수 없음) 그 DB 캐시 경로를 못 쓴다 - 대신 그 순간 라이브로 받은
match_details(routers/teams.py::get_team_analysis가 이미 받아놓은 것)의 rounds를
그대로 이 함수들에 넣으면 된다(이 함수들은 rounds+our_puuids/our_color만 있으면
되고 DB/team_id에 의존하지 않는다). 그래서 공유 모듈로 뺐다 - 우리팀/상대팀 양쪽
경로가 "라운드 페이즈 계산"이라는 같은 정의를 쓰게 하기 위함.
"""

# 팀 평균 loadout_value(경제력)가 이 아래면 에코 라운드로 판정하는 휴리스틱 임계값.
# 공식 정의가 아니며, 다운스케일 무기(사이드암 위주) 구간을 대략 겨냥한 값이다.
ECO_THRESHOLD = 2000


def round_segments(round_count: int) -> list[tuple[int, int]]:
    """공격/수비가 바뀌지 않는 구간 경계. 정규시간은 12라운드씩(0-11, 12-23), 연장은
    2라운드씩(24-25, 26-27, ...) 스왑하는 표준 룰을 따른다."""
    segments = []
    idx = 0
    while idx < round_count:
        end = min(idx + 12, 24, round_count) if idx < 24 else min(idx + 2, round_count)
        segments.append((idx, end))
        idx = end
    return segments


def determine_team_color(rounds: list, team_puuids: set[str]) -> str | None:
    """rounds[i].player_stats[].player_team/player_puuid로 이 팀이 이 매치에서
    "Red"/"Blue" 중 어느 색이었는지 확인. 라운드마다 전체 로스터의 player_stats가 항상
    있어서(액션 여부와 무관) 첫 라운드에서 대부분 바로 확정된다."""
    for rnd in rounds:
        for ps in (rnd.get("player_stats") or []):
            if ps.get("player_puuid") in team_puuids and ps.get("player_team"):
                return ps["player_team"]
    return None


def segment_attackers(rounds: list, segments: list[tuple[int, int]]) -> dict[tuple[int, int], str | None]:
    result: dict[tuple[int, int], str | None] = {}
    for seg in segments:
        attacker = None
        for i in range(seg[0], seg[1]):
            rnd = rounds[i]
            if rnd.get("bomb_planted"):
                planted_by = (rnd.get("plant_events") or {}).get("planted_by") or {}
                if planted_by.get("team"):
                    attacker = planted_by["team"]
                    break
        result[seg] = attacker
    return result


def round_kill_events(rnd: dict) -> list[dict]:
    """라운드 하나의 모든 킬 이벤트를 시간순으로. player_stats[].kill_events는 그
    선수 본인이 낸 킬만 담고 있어 전체를 모으려면 로스터 전원의 목록을 합쳐야 한다."""
    events: list[dict] = []
    for ps in (rnd.get("player_stats") or []):
        events.extend(ps.get("kill_events") or [])
    return sorted(events, key=lambda k: k.get("kill_time_in_round") or 0)


def analyze_rounds(rounds: list, team_color: str) -> list[dict]:
    """라운드 하나하나를 이 팀(team_color) 관점의 레코드로 변환 - aggregate_round_phase의
    입력. 여러 매치에 걸쳐 이 레코드 리스트를 이어붙인 뒤 한 번에 집계하면 된다."""
    segments = round_segments(len(rounds))
    attackers = segment_attackers(rounds, segments)

    records = []
    for i, rnd in enumerate(rounds):
        seg = next(s for s in segments if s[0] <= i < s[1])
        attacker = attackers[seg]
        we_attacked = None if attacker is None else (attacker == team_color)

        winning_team = rnd.get("winning_team")
        we_won = None if not winning_team else (winning_team == team_color)

        our_loadouts = [
            (ps.get("economy") or {}).get("loadout_value")
            for ps in (rnd.get("player_stats") or [])
            if ps.get("player_team") == team_color and (ps.get("economy") or {}).get("loadout_value") is not None
        ]
        is_eco = (sum(our_loadouts) / len(our_loadouts) < ECO_THRESHOLD) if our_loadouts else None

        kills = round_kill_events(rnd)
        opening = kills[0] if kills else None
        got_fb = (opening.get("killer_team") == team_color) if opening else None
        got_fd = (opening.get("victim_team") == team_color) if opening else None

        plant = rnd.get("plant_events") or {}
        planted_by = plant.get("planted_by") or {}
        we_planted = bool(planted_by.get("team")) and planted_by.get("team") == team_color
        plant_site = plant.get("plant_site") if we_planted else None
        plant_time = plant.get("plant_time_in_round") if we_planted else None

        records.append({
            "we_won": we_won,
            "we_attacked": we_attacked,
            "is_pistol": i in (0, 12),
            "is_eco": is_eco,
            "got_fb": got_fb,
            "got_fd": got_fd,
            "plant_site": plant_site,
            "plant_time_ms": plant_time,
        })
    return records


def pct(wins: int, losses: int) -> int:
    total = wins + losses
    return round(wins / total * 100) if total else 0


def aggregate_round_phase(records: list[dict]) -> tuple[dict, int, int]:
    """analyze_rounds()가 만든 레코드들(매치 여러 개를 이어붙인 것도 가능)을 집계해
    {atkWinRate, defWinRate, pistolWinRate, ecoWinRate, fbWinPct, fdLosePct}와
    (전체 공수 라운드 승수, 패수)를 반환한다."""
    atk_w = atk_l = def_w = def_l = pistol_w = pistol_l = eco_w = eco_l = 0
    fb_rounds = fb_wins = fd_rounds = fd_losses = 0
    for r in records:
        if r["we_won"] is not None:
            if r["we_attacked"] is True:
                atk_w += r["we_won"]
                atk_l += not r["we_won"]
            elif r["we_attacked"] is False:
                def_w += r["we_won"]
                def_l += not r["we_won"]
            if r["is_pistol"]:
                pistol_w += r["we_won"]
                pistol_l += not r["we_won"]
            if r["is_eco"]:
                eco_w += r["we_won"]
                eco_l += not r["we_won"]
        if r["got_fb"]:
            fb_rounds += 1
            fb_wins += bool(r["we_won"])
        if r["got_fd"]:
            fd_rounds += 1
            fd_losses += r["we_won"] is False

    return {
        "atkWinRate": pct(atk_w, atk_l),
        "defWinRate": pct(def_w, def_l),
        "pistolWinRate": pct(pistol_w, pistol_l),
        "ecoWinRate": pct(eco_w, eco_l),
        "fbWinPct": round(fb_wins / fb_rounds * 100) if fb_rounds else 0,
        "fdLosePct": round(fd_losses / fd_rounds * 100) if fd_rounds else 0,
    }, atk_w + def_w, atk_l + def_l
