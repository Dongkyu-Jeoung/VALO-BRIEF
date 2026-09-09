import os
import sys
import requests
import time
import pandas as pd
from urllib import parse
from threading import Semaphore
from pathlib import Path
from dotenv import load_dotenv

from services.henrik_api import HenrikRateLimitError
from services.rate_limiter import throttle_sync

# services/henrik_api.py와 같은 .env(HENRIK_API_KEY)를 공유해서 쓴다 - 키를 소스에
# 하드코딩하지 않기 위함(예전엔 여기 평문으로 박혀 있었음, git 이력엔 남아있으니 키를
# 재발급하는 걸 권장).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API_KEY = os.getenv("HENRIK_API_KEY")

# 아래 디버그 print()들이 이모지(✅❌⚠️)를 쓰는데, Windows 콘솔 기본 인코딩(cp949)에서는
# print()가 그대로 죽는다(UnicodeEncodeError) - 이 모듈이 실제 요청 경로(routers/predict.py)에
# 물리기 전까진 아무도 안 불러서 안 드러났던 버그. 인코딩을 못 바꾸는 스트림(일부 테스트
# 러너 등)도 있어 실패해도 무시한다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}

PLATFORM = "pc"  # pc 또는 console

# HenrikDev Basic Key 기준 분당 30 요청 제한. 안전하게 2.2초 간격(분당 약 27회) + 429 발생 시 재시도.
MAX_CONCURRENT_REQUEST = 6
API_SEMAPHORE = Semaphore(MAX_CONCURRENT_REQUEST)
MAX_RETRIES_ON_429 = 5

# 레이트리밋 카운터는 services/rate_limiter.py로 통합했다 - services/henrik_api.py(일반
# 검색/프로필 트래픽)도 같은 Henrik 키의 같은 버킷을 쓰는데, 예전엔 이 파일이 따로 카운터를
# 갖고 있어서 두 클라이언트가 각자 "나는 28/분 이하"라고 안심해도 합치면 실제 한도(30/분)를
# 넘겨 429를 받을 수 있었다(승부예측_성능_분석.md 3번 참고). 이제 throttle_sync() 하나가
# 두 클라이언트가 보낸 요청을 모두 같이 센다.

PLAYER_FEATURES = [
    "rr",
    "acs",
    "adr",
    "kast",
    "kd",
    "headshot_pct",
    "bodyshot_pct",
    "first_blood",
    "first_death",
    "kills",
    "deaths",
    "assists"
]

# 매치 상세 API 캐시 (같은 매치를 여러 시드 플레이어가 공유할 때 중복 호출 방지)
_MATCH_DETAIL_CACHE = {}

def api_get(url: str) -> dict:
    """
    모든 HenrikDev API 호출을 통과시키는 공통 함수.
    - 매 호출 사이 REQUEST_INTERVAL_SEC만큼 대기해 분당 요청 한도(Basic Key: 30/min)를 넘지 않도록 한다.
    - 429(Rate Limited)를 받으면 지수 백오프로 재시도하고, 그래도 안 되면 HenrikRateLimitError를
      던진다(services/henrik_api.py와 동일한 예외 - main.py의 전역 핸들러가 503으로 응답).
      예전엔 재시도를 다 쓰고도 마지막 429 응답을 그냥 반환했는데, 호출부(get_puuid_by_riot_id
      등)가 status_code != 200을 전부 "존재하지 않음"으로 처리해서 실제로는 레이트리밋일 때도
      "PUUID 조회 실패"처럼 보였다(승부예측_성능_분석.md 3번 참고).
    """
    res = None
    for attempt in range(MAX_RETRIES_ON_429 + 1):
        throttle_sync()
        with API_SEMAPHORE:

            res = requests.get(url, headers=HEADERS, timeout=(5, 30))

        if res.status_code == 429:

            wait = 2 ** attempt
            time.sleep(wait)
            continue

        return res

    print(f"  ❌ 429 재시도 한도 초과, 요청 포기: {url}")
    raise HenrikRateLimitError(url)


def get_puuid_by_riot_id(name: str, tag: str) -> str:
    encoded_name = parse.quote(name)
    encoded_tag = parse.quote(tag)
    url = f"https://api.henrikdev.xyz/valorant/v2/account/{encoded_name}/{encoded_tag}"

    res = api_get(url)
    if res.status_code == 200:
        puuid = res.json().get("data", {}).get("puuid")
        print(f"✅ [{name}#{tag}] PUUID 획득 성공")
        return puuid
    else:
        print(f"❌ [{name}#{tag}] 계정 조회 실패 ({res.status_code})")
        return None


def get_matches_v4(region: str, platform: str, puuid: str, total_matches: int, page_size: int = 10) -> list:
    """
    Henrik v4 Match API
    - 원하는 경기 수(total_matches)만큼만 페이지네이션
    - 마지막 페이지는 남은 개수만 요청
    """

    matches = []
    start = 0

    while len(matches) < total_matches:

        # 이번 요청에서 실제로 가져올 개수
        current_size = min(page_size, total_matches - len(matches))

        url = (
            f"https://api.henrikdev.xyz/valorant/v4/by-puuid/matches/"
            f"{region}/{platform}/{puuid}"
            f"?size={current_size}&start={start}"
        )

        res = api_get(url)

        if res.status_code != 200:
            print(
                f"  ⚠️ 매치 목록 API 호출 실패 "
                f"(start={start}, Status Code: {res.status_code})"
            )
            break

        page_data = res.json().get("data", [])

        if page_data:
            print("\n===== MATCH LIST SAMPLE =====")

            for m in page_data[:5]:
                match_id = (m.get("metadata") or {}).get("match_id")
                started_at = m.get("metadata", {}).get("started_at")

                print(match_id, started_at)

            print("============================\n")

        if not page_data:
            print(f"  └─ start={start} 이후 더 이상 매치 없음")
            break

        matches.extend(page_data)

        print(
            f"  └─ start={start} 페이지에서 "
            f"{len(page_data)}개 수집 (누적 {len(matches)}개)"
        )

        start += current_size

    return matches


def get_match_detail_v4(region: str, match_id: str) -> dict:
    """
    ACS/ADR/KAST/First Blood 계산에 필요한 라운드 단위 상세 데이터를 가져온다.
    matchlist 응답에는 없는 정보이므로 매치당 별도 호출이 필요하다.
    """
    if match_id in _MATCH_DETAIL_CACHE:
        return _MATCH_DETAIL_CACHE[match_id]

    url = f"https://api.henrikdev.xyz/valorant/v4/match/{region}/{match_id}"
    res = api_get(url)

    if res.status_code != 200:
        print(f"  ⚠️ Match {match_id} 상세 정보 호출 실패 (Status Code: {res.status_code})")
        return None

    detail = res.json().get("data", {})
    _MATCH_DETAIL_CACHE[match_id] = detail
    return detail


# def get_rr_history_map(region: str, puuid: str) -> dict:
#     """
#     match_id -> {"rr_after": ..., "rr_change": ..., "elo_after": ...} 매핑을 만든다.
#     stored-mmr-history는 match_id를 직접 포함하고 있어 날짜 기반 추정이 필요 없다.
#     경쟁전이 아닌 매치는 애초에 이 목록에 없으므로 결과에서 빠지고, 이후 NaN 처리된다.

#     elo_after: tier(티어)를 하나로 이어붙인 연속 스케일 값 (예: tier_id*100+rr 형태의 관례적 계산).
#     tier마다 0~100으로 리셋되는 rr과 달리, elo는 티어 경계 없이 실력 순서를 그대로 반영하므로
#     티어 간 비교나 모델 feature로는 rr_after보다 elo_after를 우선 사용하는 것을 권장한다.
#     (단, Riot 공식 스펙이 아닌 HenrikDev 측 파생값이며 레디언트 구간은 RR 상한이 없어 예외적일 수 있음)
#     """
#     url = f"https://api.henrikdev.xyz/valorant/v1/by-puuid/stored-mmr-history/{region}/{puuid}"
#     res = api_get(url)

#     if res.status_code != 200:
#         print(f"  ⚠️ RR(MMR) 히스토리 호출 실패 (Status Code: {res.status_code})")
#         return {}

#     entries = res.json().get("data", [])

#     # ===== DEBUG =====
#     if entries:
#         print("\n===== RR ENTRY SAMPLE =====")
#         print(entries[0])
#         print("===========================\n")
    
#     rr_map = {}

#     for e in entries:
#         # Henrik API의 match_id를 Match Detail 형식과 맞춤
#         match_id = e.get("match_id")
#         if not match_id:
#             continue

#         match_id = match_id.replace("KR_", "").lower()

#         rr_map[match_id] = {
#             "rr_after": e.get("rr"),
#             "rr_change": e.get("rr_change"),
#             "elo_after": e.get("elo")
#         }
#     print("\n=== RR MAP DEBUG ===")
#     print("RR 개수 :", len(rr_map))
#     print("RR Keys :", list(rr_map.keys())[:5])
#     print("====================")

#     return rr_map


# 팀원이 죽은 뒤 이 시간(ms) 안에 그 킬러를 처치하면 "트레이드"로 인정 (업계 통용 근사치: 3~5초)
TRADE_WINDOW_MS = 5000


def _get_rounds_played(match_detail: dict) -> int:
    """
    공식 스키마에는 rounds_played가 명시적으로 없어 두 가지 방법으로 계산 후 교차 검증한다.
    """
    rounds_list_count = len(match_detail.get("rounds") or [])

    teams = match_detail.get("teams") or []
    teams_round_count = 0
    if teams:
        t0 = teams[0].get("rounds", {})
        teams_round_count = (t0.get("won") or 0) + (t0.get("lost") or 0)

    if teams_round_count and rounds_list_count and teams_round_count != rounds_list_count:
        print(f"  ⚠️ rounds_played 불일치 감지 (rounds 배열 길이: {rounds_list_count}, teams 합계: {teams_round_count}) — rounds 배열 길이 기준으로 진행")

    return rounds_list_count or teams_round_count


def compute_advanced_player_stats(match_detail: dict, target_puuid: str) -> dict:
    """
    matchlist(간이 목록)에는 없는 acs, adr, kast, first_blood, first_death를
    v4/match 공식 스키마 기준으로 계산한다.

    - acs, adr: players[].stats.score / damage.dealt를 rounds_played로 나눠서 계산 (매치 전체 누적값 기반)
    - kast, first_blood, first_death: 최상위 data.kills 배열(라운드 번호 + 라운드 내 타이밍 포함)을 라운드별로 그룹핑해서 계산

    ⚠️ KAST에 트레이드 판정을 포함했습니다: 팀원이 죽은 뒤 TRADE_WINDOW_MS(기본 5초) 안에
    그 킬러가 처치되면, 죽은 팀원의 KAST에 "Traded"로 반영됩니다. 이 5초 기준은 공식 정의가
    아니라 업계에서 흔히 쓰는 근사치이므로, 필요시 TRADE_WINDOW_MS 값을 조정하세요.
    ⚠️ first_blood/first_death는 "라운드별 오프닝 킬/데스 횟수"로 해석했습니다
    (경기 전체 통틀어 첫 킬 1회를 의미하는 것이 아닙니다).
    """
    rounds_played = _get_rounds_played(match_detail)
    if rounds_played == 0:
        return {"acs": None, "adr": None, "kast": None, "first_blood": None, "first_death": None}

    # ACS / ADR: 매치 전체 누적값(top-level stats)을 라운드 수로 나눔
    target_player = next((p for p in match_detail.get("players", []) if p.get("puuid") == target_puuid), None)
    if not target_player:
        return {"acs": None, "adr": None, "kast": None, "first_blood": None, "first_death": None}

    total_score = (target_player.get("stats", {}) or {}).get("score", 0) or 0
    total_damage_dealt = ((target_player.get("stats", {}) or {}).get("damage", {}) or {}).get("dealt", 0) or 0

    acs = round(total_score / rounds_played, 1)
    adr = round(total_damage_dealt / rounds_played, 1)

    # KAST / First Blood / First Death: 최상위 kills 배열을 라운드별로 그룹핑
    all_kills = match_detail.get("kills") or []
    kills_by_round = {}
    for k in all_kills:
        kills_by_round.setdefault(k.get("round"), []).append(k)

    kast_rounds = 0
    first_bloods = 0
    first_deaths = 0

    # 킬이 없는 라운드도 생존으로 집계한다(DB 저장 계산과 동일).
    for round_id in range(rounds_played):
        round_kills = kills_by_round.get(round_id, [])
        if not round_kills:
            kast_rounds += 1
            continue
        round_kills_sorted = sorted(round_kills, key=lambda k: k.get("time_in_round_in_ms", float("inf")))

        # 오프닝 킬/데스
        opening_kill = round_kills_sorted[0]
        opening_killer = (opening_kill.get("killer") or {}).get("puuid")
        opening_victim = (opening_kill.get("victim") or {}).get("puuid")
        if opening_killer == target_puuid:
            first_bloods += 1
        if opening_victim == target_puuid:
            first_deaths += 1

        # 이번 라운드 내 이 선수의 킬/데스/어시스트
        my_kill = next((k for k in round_kills_sorted if (k.get("killer") or {}).get("puuid") == target_puuid), None)
        my_death = next((k for k in round_kills_sorted if (k.get("victim") or {}).get("puuid") == target_puuid), None)
        got_assist = any(
            target_puuid in [a.get("puuid") for a in (k.get("assistants") or [])]
            for k in round_kills_sorted
        )
        survived = my_death is None

        # 트레이드 판정: 내가 죽었다면, 나를 죽인 사람이 곧바로(TRADE_WINDOW_MS 이내) 처치됐는지 확인
        traded = False
        if my_death is not None:
            killer_of_me = (my_death.get("killer") or {}).get("puuid")
            death_time = my_death.get("time_in_round_in_ms", 0)
            for k in round_kills_sorted:
                if (k.get("victim") or {}).get("puuid") == killer_of_me:
                    revenge_time = k.get("time_in_round_in_ms", 0)
                    if 0 <= (revenge_time - death_time) <= TRADE_WINDOW_MS:
                        traded = True
                        break

        if my_kill is not None or got_assist or survived or traded:
            kast_rounds += 1

    kast = round((kast_rounds / rounds_played) * 100, 1)

    return {
        "acs": acs,
        "adr": adr,
        "kast": kast,
        "first_blood": first_bloods,
        "first_death": first_deaths,
    }


def extract_player_rows_from_match(match_detail: dict, seed_puuid: str) -> list:
    """
    v4/match 공식 스키마(match_detail) 기준으로 5v5 선수 10명 각각에 대해 1행씩 만든다.
    (matchlist가 아니라 상세 엔드포인트 응답 하나만을 신뢰 가능한 소스로 사용)
    """
    try:
        metadata = match_detail.get("metadata", {})
        match_id = metadata.get("match_id") or "UNKNOWN_ID"
        map_name = (metadata.get("map") or {}).get("name", "Unknown Map")
        mode = (metadata.get("queue") or {}).get("name", "Unknown Mode")

        started_at = metadata.get("started_at")

        if mode.lower() in ["deathmatch", "team deathmatch", "escalation"]:
            print(f"  ⚠️ Match {match_id}: 지원하지 않는 모드 ({mode}) 스킵")
            return []

        # 팀별 승패 판정 (공식 스키마: teams는 리스트, 각 항목에 team_id/won)
        team_won = {t.get("team_id", ""): bool(t.get("won")) for t in (match_detail.get("teams") or [])}

        players = match_detail.get("players", [])
        if not players:
            print(f"  ⚠️ Match {match_id}: 플레이어 데이터 없음")
            return []

        if len(players) != 10:
            print(f"  ⚠️ Match {match_id} [{mode}]: 10명(5v5) 인원 불일치, 스킵 (실제 {len(players)}명)")
            return []

        rows = []
        for p in players:
            puuid = p.get("puuid")
            team = p.get("team_id", "Unknown")
            agent = (p.get("agent") or {}).get("name", "Unknown")

            stats = p.get("stats") or {}
            kills = stats.get("kills") or 0
            deaths = stats.get("deaths") or 0
            assists = stats.get("assists") or 0
            headshots = stats.get("headshots") or 0
            bodyshots = stats.get("bodyshots") or 0
            legshots = stats.get("legshots") or 0
            total_shots = headshots + bodyshots + legshots

            kd = round(kills / max(1, deaths), 2)
            headshot_pct = round((headshots / total_shots) * 100, 1) if total_shots > 0 else 0.0
            bodyshot_pct = round((bodyshots / total_shots) * 100, 1) if total_shots > 0 else 0.0

            advanced = compute_advanced_player_stats(match_detail, puuid)

            rows.append({
                "match_id": match_id,
                "started_at": started_at,
                "map": map_name,
                "mode": mode,
                "puuid": puuid,
                "name": p.get("name"),
                "tag": p.get("tag"),
                "team": team,
                "agent": agent,
                "win": 1 if team_won.get(team, False) else 0,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "kd": kd,
                "headshot_pct": headshot_pct,
                "bodyshot_pct": bodyshot_pct,
                "acs": advanced["acs"],
                "adr": advanced["adr"],
                "kast": advanced["kast"],
                "first_blood": advanced["first_blood"],
                "first_death": advanced["first_death"],
            })

        return rows

    except Exception as e:
        print(f"  ❌ Match 파싱 중 오류 발생: {e}")
        return []

def collect_unique_puuids(matches):

    puuids = set()

    for match in matches:
        players = match.get("players", [])

        for p in players:
            puuid = p.get("puuid")
            if puuid:
                puuids.add(puuid)

    return puuids
