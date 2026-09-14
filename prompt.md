# VALORANT Premier 승부예측 시스템 구조 전환

당신은 현재 존재하는 React + FastAPI + XGBoost 기반 VALORANT 승부예측 프로젝트를 분석하고 수정하는 개발 에이전트다.

중요한 원칙은 **기존 프로젝트 구조를 최대한 유지하면서 필요한 부분만 최소 수정**하는 것이다.

다른 팀원이 작성한 Frontend 및 공통 Backend 코드를 임의로 대규모 리팩터링하지 말고, 승부예측 기능과 직접적으로 관련된 코드만 수정한다.

---

## 1. 프로젝트 기존 구조

기술 스택:

* Frontend: React + Vite
* Backend: FastAPI
* ML: XGBoost
* External API: HenrikDev VALORANT API
* Database: SQLAlchemy 기반 DB
* 기존 학습 모델: 저장된 XGBoost 모델 사용

기존 예측 구조는 대략 다음과 같다.

1. Blue Team 5명 조회
2. Red Team 5명 조회
3. 각 선수의 최근 경기 조회
4. Player Feature Engineering
5. Team Feature Engineering
6. XGBoost `predict_proba()`
7. 승률 반환
8. React PredictBox에 출력

기존 방식은 각 플레이어의 최근 경기들을 개별적으로 조회하기 때문에 Henrik API 호출 수가 많고, Deathmatch/TDM 등 사용할 수 없는 경기가 포함될 경우 추가 검색이 반복되어 예측 시간이 너무 길어지는 문제가 있다.

---

# 2. 새로운 프로젝트 방향

예측 데이터의 기준을 **개별 플레이어 최근 경기 → Premier 팀의 최근 Premier 경기**로 변경한다.

새로운 전체 흐름은 다음과 같다.

```text
Blue Premier Team
        ↓
Premier History API
        ↓
최근 Premier 경기 3~5개 match_id
        ↓
각 Match Detail 조회
        ↓
선수별 경기 스탯 추출
        ↓
Player / Team Feature Engineering
        │
        │
        ├──────────────┐
        │              │
Red Premier Team       │
        ↓              │
동일 과정              │
        │              │
        └──────┬───────┘
               ↓
기존 XGBoost 입력 Feature 생성
               ↓
model.predict_proba()
               ↓
Blue / Red 최종 승률
```

---

# 3. Premier 경기 사용 규칙

각 팀마다 Premier History를 조회한다.

경기 수 정책:

* 최근 Premier 경기 5경기 이상 → 최신 5경기 사용
* 4경기 → 4경기 사용
* 3경기 → 3경기 사용
* 3경기 미만 → 예측 중단

3경기 미만일 경우 Backend에서 명확한 오류 응답을 반환하여 Frontend에서 다음과 같은 안내를 표시할 수 있어야 한다.

"최근 Premier 경기 데이터가 부족하여 승부예측을 진행할 수 없습니다. 최소 3경기의 Premier 경기 기록이 필요합니다."

---

# 4. 중요한 모델 사용 원칙

기존 XGBoost 모델을 유지한다.

하지만 **Premier 경기 하나하나를 XGBoost에 개별 입력하여 경기력 점수를 만든 뒤 평균내는 방식은 사용하지 않는다.**

반드시 다음 구조를 사용한다.

```text
최근 Premier 3~5경기
        ↓
경기별 Player Stats 추출
        ↓
최근 경기 Feature 생성
        ↓
5명 Team Feature 집계
        ↓
Blue / Red / Diff Feature 생성
        ↓
XGBoost 1회 실행
```

즉 XGBoost는 최종 양 팀 비교 단계에서 한 번만 실행한다.

---

# 5. 기존 모델 Feature 구조

현재 모델의 최종 입력은 다음 18개 Feature이다.

```text
blue_recent_acs
red_recent_acs
diff_recent_acs

blue_recent_kd
red_recent_kd
diff_recent_kd

blue_recent_kast
red_recent_kast
diff_recent_kast

blue_recent_headshot_pct
red_recent_headshot_pct
diff_recent_headshot_pct

blue_recent_winrate
red_recent_winrate
diff_recent_winrate

blue_duelist_count
red_duelist_count
diff_duelist_count
```

가능한 경우 기존 `team_feature.py`와 Feature column order를 그대로 유지한다.

Feature 이름이나 순서를 임의로 바꾸지 않는다.

---

# 6. 최근 Premier 경기에서 생성해야 할 Player Feature

각 플레이어에 대해 최근 Premier 3~5경기의 다음 값을 집계한다.

```text
recent_acs
recent_kd
recent_kast
recent_headshot_pct
recent_winrate
agent
```

가능한 한 기존 학습 과정에서 사용한 계산 방식을 그대로 재사용한다.

예:

```text
최근 경기들의 ACS 평균
최근 경기들의 KD 평균
최근 경기들의 KAST 평균
최근 경기들의 HS% 평균
최근 경기 승/패 평균
Agent 정보 → Duelist Count 계산
```

---

# 7. 중요한 데이터 처리 기준

Premier History에서 가져온 match_id를 사용하기 때문에 일반 플레이어 Match History에서 발생하던 다음 문제를 최소화한다.

```text
Deathmatch
Team Deathmatch
Escalation
기타 모델에 사용할 수 없는 일반 경기
```

하지만 Match Detail API 응답 자체가 없거나 필요한 데이터가 누락된 경우를 대비한 방어 코드는 유지한다.

예:

```python
if detail is None:
    ...
```

다만 무한하게 더 과거 경기를 재검색하는 구조는 만들지 않는다.

Premier History에서 선택한 최대 5경기를 기준으로 처리한다.

---

# 8. 데이터 누수 방지

학습 또는 평가 데이터를 새로 생성하는 경우 다음 규칙을 반드시 지킨다.

예측 대상 Match N을 예측할 때 Match N 자체의 결과 데이터를 Feature로 사용하면 안 된다.

올바른 구조:

```text
Match N 이전 Premier 경기
→ Feature

Match N
→ Target
```

잘못된 구조:

```text
Match N의 ACS/KD/KAST
→ Match N의 승패 예측
```

이런 데이터 누수가 발생하지 않도록 검증한다.

---

# 9. 기존 XGBoost 사용에 대한 주의사항

기존 모델은 Premier 경기만으로 학습된 모델이 아니다.

따라서 새로운 Premier 기반 Feature 입력은 기존 학습 분포와 차이가 발생할 수 있다.

이를 고려하여:

1. 기존 모델 파일은 유지한다.
2. Feature 구조도 최대한 유지한다.
3. 새로운 Premier 입력 데이터를 이용한 예측 결과를 검증한다.
4. 가능하다면 기존 test/evaluation 코드로 다음 지표를 다시 측정한다.

```text
Accuracy
ROC-AUC
LogLoss
Brier Score
```

모델 재학습은 내가 별도로 요청하지 않는 이상 먼저 수행하지 않는다.

---

# 10. API 호출 최적화

목표 중 하나는 API 호출량 감소와 승부예측 속도 개선이다.

기존 방식처럼 선수 10명의 최근 경기를 각각 검색하지 않는다.

권장 구조:

```text
Blue:
Premier History 1회
Match Detail 최대 5회

Red:
Premier History 1회
Match Detail 최대 5회
```

즉 이상적인 최대 호출 구조는 대략:

```text
Premier History 2회
Match Detail 최대 10회
```

정도이다.

같은 match_id에 대한 중복 요청은 캐시가 있다면 재사용한다.

---

# 11. 코드 수정 원칙

코드를 수정하기 전에 프로젝트 구조부터 분석한다.

특히 다음 파일들을 먼저 찾고 역할을 분석한다.

```text
routers/predict.py
services/predict_service.py
ml/predictor.py
ml/rolling.py
ml/team_feature.py
ml/model_loader.py
valorant_git.py
api/prediction.js
MatchPredictionPage/index.jsx
PredictBox.jsx
```

파일명이 실제 프로젝트와 다르면 동일 역할의 파일을 찾아 사용한다.

수정 원칙:

* 기존 코드를 최대한 재사용
* 불필요한 파일 삭제 금지
* 대규모 리팩터링 금지
* Frontend API contract 임의 변경 금지
* 기존 XGBoost Feature 순서 변경 금지
* 다른 팀원이 작성한 UI/분석 기능 최소 수정
* 기존 Mock/Fallback 구조를 함부로 제거하지 말 것

---

# 12. 작업 순서

반드시 다음 순서로 진행한다.

### STEP 1

현재 프로젝트에서 Premier 팀 조회 및 History 관련 Henrik API 함수가 이미 존재하는지 찾는다.

### STEP 2

Premier History 응답 구조를 확인하고 최근 Premier 경기의 match_id를 최대 5개 추출하는 함수를 만든다.

예:

```python
get_recent_premier_match_ids(...)
```

반환:

```python
[
    match_id_1,
    match_id_2,
    match_id_3,
    ...
]
```

### STEP 3

최근 경기 수가 3개 미만이면 예측 불가 처리한다.

### STEP 4

각 match_id의 Match Detail을 조회한다.

### STEP 5

해당 Premier 팀 소속 선수 5명의 스탯만 추출한다.

### STEP 6

최근 Premier 3~5경기를 이용하여 기존 Player Feature 구조를 생성한다.

### STEP 7

Blue / Red 각각 5명의 Player Feature를 `build_team_feature()`에 전달한다.

### STEP 8

기존 XGBoost 모델의 `predict_proba()`를 실행한다.

### STEP 9

기존 FastAPI 응답 형식을 최대한 유지한다.

### STEP 10

Frontend가 기존과 동일하게 승률을 표시하는지 확인한다.

---

# 13. 디버깅 로그

개발 과정에서 다음 내용을 확인할 수 있도록 간결한 로그를 추가한다.

```text
[PREMIER HISTORY]
team=...
matches_found=...

[PREMIER MATCH]
match_id=...

[PLAYER FEATURE]
puuid=...
recent_acs=...
recent_kd=...

[TEAM FEATURE]
blue_recent_acs=...
red_recent_acs=...
...

[PREDICTION]
blue_probability=...
```

완성 후 불필요하게 많은 디버그 로그는 제거하거나 개발 모드에서만 사용하도록 한다.

---

# 14. 최종 목표

최종 승부예측 시스템의 데이터 흐름은 반드시 다음 구조를 목표로 한다.

```text
React
   ↓
FastAPI Predict Endpoint
   ↓
Blue Premier History
Red Premier History
   ↓
각 팀 최근 Premier 3~5경기
   ↓
Match Detail
   ↓
선수 스탯
   ↓
기존 방식과 호환되는 Player Feature
   ↓
기존 Team Feature Engineering
   ↓
기존 18개 Feature
   ↓
저장된 XGBoost Model
   ↓
predict_proba()
   ↓
Blue / Red 승률
   ↓
기존 React PredictBox
```

가장 중요한 목적은 다음 세 가지이다.

1. 기존의 선수별 최근 경기 API 요청 구조를 제거하여 API 호출량과 로딩 시간을 줄인다.
2. 실제 Premier 팀이 함께 플레이한 최근 경기력을 승부예측에 반영한다.
3. 기존 XGBoost 모델과 Frontend 구조를 최대한 보존하여 팀 프로젝트의 다른 기능에 미치는 영향을 최소화한다.

작업을 시작할 때 바로 코드를 대규모 수정하지 말고, 먼저 현재 프로젝트의 관련 파일과 데이터 흐름을 분석한 뒤 **어떤 파일을 왜 수정해야 하는지 정리하여 제시하고**, 그 다음 최소 수정 방식으로 구현을 진행하라.
