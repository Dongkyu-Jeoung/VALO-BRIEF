// ============================================================
// API 기본 설정
// ------------------------------------------------------------
// - VITE_API_BASE_URL이 비어있으면(개발 초기, 서버 없음) => 무조건 mock 사용
// - 값이 채워져 있으면 실제 fetch를 시도하고, 실패(네트워크 에러/4xx/5xx)하면
//   콘솔에 경고만 남기고 mock으로 자동 폴백합니다.
// - FastAPI 서버가 준비되면 .env.development 의 VITE_API_BASE_URL만 채우면 됩니다.
//   (컴포넌트/페이지 코드는 전혀 수정할 필요 없음)
// ============================================================

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const USE_MOCK_ONLY = API_BASE_URL === '';

// 실제 백엔드가 뜨면 아래 지연시간(ms)은 지워도 됩니다.
// mock 데이터를 쓸 때 로딩 스피너 등 UI 확인을 위해 약간의 지연을 흉내냅니다.
export const MOCK_DELAY_MS = 250;

// 임시 조치: 승부예측(ML) 파이프라인(GET /api/predict/{team_name}/{team_tag})이 Henrik
// 레이트리밋 한도 때문에 실측 몇 분씩 걸려서(server/승부예측_성능_분석.md 참고) 백엔드
// 작업 중인 동안 이 엔드포인트만 mock으로 대체한다 - api/prediction.js의 fetchPrediction만
// 이 값을 참고한다. recentOpponent/teamAnalysis/teamProfile을 포함한 나머지는 전부 실제
// 백엔드를 그대로 쓴다. 백엔드 작업이 끝나면 이 값을 false로 되돌리면 된다.
export const FORCE_MOCK_PREDICTION = true;
