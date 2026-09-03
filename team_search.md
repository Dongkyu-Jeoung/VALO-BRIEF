# 팀 검색(Team Search) 개발 현황

> 이 문서는 팀 검색 기능의 진행 상황을 추적합니다. **1차로 "팀 프로필 상세 페이지"(메인화면 팀 검색 → 진입)만 구현했고, 3초 퀵분석 팝업(`quick-analysis`)은 범위 밖입니다.**
> 회귀테스트가 여러 라운드에 걸쳐 진행되면서 문서가 너무 길어져, 3번 섹션(회귀테스트)을 **매 라운드 기록 대신 "지금 기준 최종 상태" 요약**으로 정리했습니다. 세부 조사/시행착오 과정이 필요하면 git 히스토리를 참고하세요.

---

## 0. 현황 한눈에 보기

| 구분                                        | 상태                                                                         |
| ------------------------------------------- | ------------------------------------------------------------------------------ |
| 개인 검색 (존재확인 → 프로필 → 모드별 스탯) | ✅ 완료 (`search.py`, `players.py`, `player_profile.py`, `riot_accounts.py`) |
| 팀 검색 → 존재 확인만                       | ✅ 완료 (`search.py: check_team_exists`, 백그라운드 프리페치 포함)           |
| **팀 검색 → 팀 프로필 상세 페이지**         | ✅ 완료 (`routers/teams.py`, `services/team_profile.py`)                     |
| 팀 검색 → 3초 퀵분석 팝업                   | ⬜ 백엔드 미구현 (프론트는 `quickAnalysisMock`으로 대체 중 - 범위 아님)       |
| 미가입 팀 데이터 DB 캐싱                    | ⬜ 의도적으로 미구현 - `teams` 테이블엔 절대 저장 안 함(4-2 참고)             |

프론트는 `withFallback()`으로 실패 시 mock을 쓰도록 되어 있어서(`USE_MOCK_ONLY` / try-catch), **백엔드만 연동하면 프론트 코드 수정 없이 바로 실 데이터로 전환됨.**

---

## 1. 개인검색 vs 팀검색 — 파일/함수 대조표 (혼동 방지용)

| 레이어                        | 개인검색                          | 팀검색                                                   |
| ----------------------------- | ---------------------------------- | ------------------------------------------------------- |
| 라우터                        | `routers/players.py`              | `routers/teams.py`                                       |
| 서비스(가공 로직)             | `services/player_profile.py`      | `services/team_profile.py`                                |
| Henrik 클라이언트 — 존재확인  | `henrik_api.get_account()`        | `henrik_api.get_premier_team()`                          |
| Henrik 클라이언트 — 매치 이력 | `henrik_api.get_stored_matches()` | `henrik_api.get_premier_team_history()` (포인트 변동만) |
| Henrik 클라이언트 — 매치 상세 | (불필요, stored-matches로 충분)    | `henrik_api.get_match_detail()` (v2/match, 팀 쪽만 사용) |
| 존재확인 시 백그라운드 프리페치 | `search.py: _prefetch_profile_data` | `search.py: _prefetch_team_profile_data`               |
| 공유 상수(매치 조회 개수)     | 해당 없음                          | `services/team_profile.py: MATCH_HISTORY_LIMIT` (routers/teams.py + routers/search.py가 공유) |
| DB 캐싱                       | `riot_accounts` (구현됨, KST로 저장) | **없음(의도적)** - `teams` 테이블은 회원가입 계정 전용이라 미가입 팀은 절대 저장 안 함(4-2) |
| 프론트 API 함수               | `api/players.js`                  | `api/teams.js`                                            |
| 프론트 페이지                 | `pages/PlayerProfilePage`         | `pages/TeamProfilePage`                                    |
| 존재하지 않을 때 처리         | 검색창 단계: 토스트만(페이지 이동 없음). 프로필 단계(데모 링크 등으로 직접 진입 시): mock 폴백 | 좌동 |

---

## 2. 구현 내역 (`routers/teams.py`, `services/team_profile.py`)

### 2-1. 엔드포인트

```
GET /api/teams/{team_name}/{team_tag}
```

흐름: `get_premier_team()` + `get_premier_team_history()`를 동시에 호출 → 이력에서 최근 매치 id **10개**(최신순, `MATCH_HISTORY_LIMIT`)를 뽑아 `get_match_detail()`을 전부 동시에(`asyncio.gather`) 호출 → `build_team_profile()`로 조립.

매치 상세(v2/match)는 region/platform 불필요, 건당 ~1.3MB(실측) - 여러 건은 반드시 `asyncio.gather`로 동시에 불러야 함(v4/match는 프리미어 매치에서 전부 404였음, 확인됨).

### 2-2. `build_team_profile()`이 채우는 필드

```
name, tag              ← team_info.name/tag
division                ← team_info.placement.division 원본 숫자 그대로 "디비전 N"
                           (프론트에서 teamTierKey()로 등급 아이콘 매핑 - 2-3 참고)
ratingIconUrl           ← team_info.customization.image (팀 로고, Henrik CDN URL)
recentSummary           ← 참고용(전체 시즌 누적). 화면 카드는 matchHistory로 프론트가 직접 재계산
playerRanking           ← 최근 매치 10건 로스터 스탯 평균, ACS 내림차순 top5
mapWinrates             ← matchHistory 맵별 집계 (한글 맵명)
matchHistory            ← 매치 10건: map/result/date/time/roundScore/roundsWon/roundsLost/
                           kda/adr/acs/firstBlood/mvp(한글 요원명)/season/act
actOptions               ← [{season, acts}] 실제 매치 데이터 기준, 최신순
```

**직접 결정한 부분**:
- **"우리 팀" 판별**: `match.teams.red/blue.roster.name+tag`를 대소문자 무시 비교(`_match_our_side`)
- **MVP 기준**: ACS(라운드당 평균 점수) 최고 1명 (원점수 아님 - 사용자 확인)
- **퍼스트블러드**: 라운드별 최빠른 킬의 killer가 우리 로스터인 라운드 수(`_first_blood_count`)
- **"팀 매치" 정의**: `premier_team_history.league_matches`에 있는 건 전부 포함(스크림/커스텀 구분 필드 없음)
- **역할군 라벨**: `player_profile.py`의 `ROLE_LABELS`/`_load_ref_agents()` 재사용
- **season/act**: `v2/match`의 `season_id`가 uuid라 개인 매치처럼 못 씀 → 달력 기반 추정(`_season_act_for`, 연도당 6개 Act)

### 2-3. 디비전 등급 아이콘 매핑 (`teamTierKey`, `front/src/utils/gameDataKey.js`)

라이엇 공식 Premier 안내에 따르면 Open→Intermediate→Advanced→Elite는 각 5단계, 그 위에 Contender·최상위 Invite가 있음(지역 인원수에 따라 단계 수가 줄 수 있다고도 안내됨). Henrik이 주는 `division`은 이 등급들을 관통하는 연속된 정수이고, **지역별 정확한 숫자 경계는 공식 문서에 없어서** "5단계 구조 + 주요 지역에서 관찰된 최상위 디비전(22)"을 근거로 아래처럼 추정 매핑함(실제와 다를 수 있음):

```
1~5   → open          11~15 → advanced      21   → contender
6~10  → intermediate  16~20 → elite         22+  → invite
```

`ProfileHeader.jsx`가 `teamTierKey(division)`로 `gameData.tiers.team`(open/intermediate/advanced/elite/contender/invite, `assets/images/team-tiers/`)에서 아이콘을 찾아 보여줌. 팀 로고(`ratingIconUrl`, 위쪽 아바타)와는 별개 - 이건 division 옆의 작은 등급 배지.

---

## 3. 회귀테스트 반영 사항 (최종 상태 요약)

- **라우팅**: `/teams/*`, `/players/*`는 `<ProtectedRoute>` 해제 - 로그인 없이도 프로필 조회 가능(로그인 필요한 건 승부예측/내 팀 분석뿐).
- **존재하지 않는 검색**: `checkPlayerExists`/`checkTeamExists`(`api/search.js`)는 실패해도 mock으로 대체하지 않고 에러를 그대로 던짐 → `SearchBox`/`HeaderSearchBar`/`ModalTeamSearchBar`의 기존 catch가 토스트만 띄우고 페이지 이동은 하지 않음. (반면 존재확인을 통과해 진입한 프로필 자체 조회(`fetchPlayerProfile`/`fetchTeamProfile`)는 실패 시 여전히 mock 폴백 - 데모 링크(`example#0000`, `team-ascend#ASC`)가 mock을 보여주는 것도 이 때문이며 의도된 동작.)
- **로딩 UX**: 검색창 대기 중엔 전체화면 로딩 없이 버튼이 "···"로만 바뀜(가벼운 피드백). 전체화면 로딩(`LoadingText full`, `.loading-state-full` - 헤더 80px는 안 덮고 그 아래만 덮음)은 **실제 페이지 이동이 확정된 뒤 목적지 페이지 자체가 데이터를 받아오는 동안에만** 뜸.
- **`QuickAnalysisModal`**: 데이터 도착 전 `null`을 반환해 팝업 배경조차 없이 뒤 화면(홈)이 그대로 보이던 버그 수정 - 이제 팝업 틀은 즉시 뜨고 그 안에서만 로딩 표시.
- **이미지 매핑**: 팀 로고(`ratingIconUrl`, Henrik CDN, 기존 키로 충분), 맵 썸네일(`mapKey()`), 매치별 MVP 요원(백엔드에서 한글 변환해 내려줌), 디비전 등급 아이콘(`teamTierKey()`, 2-3 참고) 전부 매핑 완료.
- **상대 팀 개인순위 표(`MiniRankTable`)**: `table-layout: fixed`로 열 너비 고정(스크롤/줄바꿈 없이 항상 폭에 맞춤). 헤더 라벨엔 말줄임표 없음, 값(선수 이름)엔 있음.
- **주요 맵 승률 표**: 3열 균등 그리드 - 맵 이름(아이콘+텍스트)은 왼쪽 정렬(길이가 달라도 아이콘 위치 고정), 승/패·승률 두 열은 가운데 정렬.
- **개인 매치 히스토리 K/D/A**: 기본 왼쪽 정렬 유지(가운데 정렬 시도했다가 사용자 요청으로 원복). 대신 `.kda-block`(`match.css`)에 고정 너비를 줘서, K/D/A 자릿수가 매치마다 달라도(예: "14/8/5" vs "6/12/3") 그 뒤에 오는 라운드 스코어(`.round-score`)가 항상 같은 위치에 오도록 함 - 팀 쪽 맵 승률 표(3-9-2/3-10-1)와 같은 종류의 "가변폭 요소 뒤 정렬 밀림" 문제였음.
- **팀검색 성능**: 개인검색과 동일하게, 존재확인(`check_team_exists`) 통과 시 팀 이력+매치상세 10건을 백그라운드로 미리 프리페치(`_prefetch_team_profile_data`).
- **DB 저장**: 미가입 팀은 `teams` 테이블에 저장하는 코드 자체가 없음(확인 완료, 4-2 참고). `riot_accounts.updated_at`은 RDS 서버 타임존(주로 UTC)과 무관하게 애플리케이션에서 KST로 계산해 명시적으로 저장하도록 수정함(`riot_accounts.py: _now_kst()`).

---

## 3-A. 헤더/메인 검색 성능 점검 (중복 모듈 · 중복 API 호출 정리)

헤더/메인화면의 개인·팀 검색이 화면부터 백엔드까지 실제로 어떤 호출을 하는지 다시 훑어서 찾은 중복을 정리함.

### 백엔드 — `get_account` 중복 호출 제거 (`routers/search.py`)

`check_player_exists`에서 region 추측이 맞은 경우, `account`를 이미 조회해놓고도 카드/칭호 프리페치 함수(`_prefetch_cosmetics`)가 내부에서 `get_account`를 **또** 불러서 실질적으로 같은 계정을 두 번 조회하고 있었음(60초 캐시/in-flight dedup 덕에 실제 중복 네트워크 호출까지 가진 않았지만, 코드상 불필요한 재조회였고 그 보장도 우연에 가까웠음). `_prefetch_cosmetics(account: dict)`가 이미 조회된 계정 객체를 직접 받도록 바꾸고, account를 모를 때만 쓰는 `_prefetch_account_and_cosmetics()`를 분리함. `_prefetch_profile_data()`에도 `account` 옵션 인자를 추가해서, 호출부가 이미 계정을 갖고 있으면 넘겨받아 재조회 없이 그대로 씀.

### 백엔드 — 참조 테이블(`ref_agents`/`ref_maps`) 프로세스 캐싱 (`services/player_profile.py`)

개인 프로필/모드별 스탯/팀 프로필 요청마다 `_load_ref_agents()`/`_load_ref_maps()`가 **매번 MySQL을 다시 조회**하고 있었음 - 이 두 테이블은 런타임에 안 바뀌는 정적 참조 데이터라 매 요청 재조회가 불필요함. 모듈 전역 캐시(`_ref_agents_cache`/`_ref_maps_cache`)로 프로세스 생존 기간 동안 한 번만 로드하도록 바꿈. 실측: 첫 호출 ~115ms(실제 DB 왕복) → 이후 호출 0ms(캐시 히트). 개인/팀 프로필 양쪽 다 이 함수를 공유해서 쓰므로 두 흐름 모두 혜택을 봄.

### 프론트 — 검색창 3곳 중복 로직을 훅 하나로 통합 (`hooks/useExistenceSearch.js`, 신규)

`SearchBox.jsx`(홈 히어로), `HeaderSearchBar.jsx`(헤더), `ModalTeamSearchBar.jsx`(퀵분석 팝업 내부) 3곳이 "형식 검사(`isValidFormat`) → 존재확인 API 호출 → 에러 토스트 → 로딩 상태" 로직을 각자 거의 똑같이 복붙해서 갖고 있었음(정규식까지 3번 중복 정의). `useExistenceSearch()` 훅으로 합치고, 존재확인 이후 실제로 하는 일(페이지 이동 vs 콜백)만 각 컴포넌트에 남김 - 세 파일 다 로직 코드가 크게 줄었고, 검색 동작을 고칠 때 한 곳만 고치면 됨.

---

## 4. 다음 단계 검토 사항

### 4-1. 디비전 등급 아이콘 정확도

2-3의 매핑은 **추정치**임(공식 문서에 지역별 정확한 division 숫자 경계가 없음). 실제 여러 팀으로 검증했을 때 등급이 이상하면 경계값(`gameDataKey.js: teamTierKey`)을 조정해야 함. `premier_tiers` DB 테이블은 여전히 비어있고 현재는 안 씀.

### 4-2. 성능 최적화 — 영구 캐싱 전략 제안 (⚠️ 코드 미반영, 검토만)

- **매치 상세(`get_match_detail`)는 완전히 영구 캐싱 가능한 데이터**(끝난 매치 결과는 안 바뀜). match_id 키로 하는 캐시 테이블(`match_cache`)이 있으면 같은 매치를 참조하는 양팀 조회가 서로 이득을 봄.
- **팀 기본 정보/이력은 자주 바뀌는 값**이라 영구 캐싱은 안 맞고, 기존 60초 TTL 캐시(`henrik_api.py`) 정도가 적당함.
- **`teams` 테이블에는 절대 캐싱하면 안 됨** - 회원가입 계정과 결합돼 있어서, 미가입 팀까지 캐싱하면 로그인 테이블 무결성이 깨짐. 현재 이 규칙은 지켜지고 있음(3번 섹션 참고).
- 결론: 로그인 붙을 때 `match_cache`(영구) + `premier_team_cache`(TTL) 두 테이블 추가를 권장.

### 4-3. 아직 안 건드린 것

- [ ] quick-analysis(3초 팝업) 백엔드
- [ ] 미가입 팀 DB 영구 캐싱(4-2, 로그인 이후) - 백그라운드 프리페치(TTL)만 있는 상태
- [ ] `MyTeamAnalysisPage`/`MatchPredictionPage`의 `StatsTab`이 재사용하는 `TeamProfileBody` 자체 로직 - mock 그대로

---

## 5. 참고 — 재사용한 것들

- `henrik_api.get_premier_team()`, `henrik_api._get()` 공통 캐싱·in-flight 로직
- `player_profile.py`의 `ROLE_LABELS`, `_load_ref_agents()`, `_load_ref_maps()` - import해서 재사용
- `front/src/utils/gameDataKey.js`의 `mapKey()`/`teamTierKey()` - 개인 프로필과 같은 패턴으로 팀 쪽에도 적용
- `front/src/hooks/useSeasonActFilter.js` - 개인 프로필의 동적 `actOptions` 지원을 팀 프로필에도 그대로 적용(훅 자체는 수정 없음)
- `front/src/hooks/useExistenceSearch.js`(신규, 3-A) - 검색창 3곳(개인/팀 공용)이 공유하는 존재확인 로직
