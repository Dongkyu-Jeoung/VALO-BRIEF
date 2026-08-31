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
