import { USE_MOCK_ONLY, MOCK_DELAY_MS } from './config';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 공통 폴백 헬퍼.
 * - 서버 주소가 설정 안 됐으면(USE_MOCK_ONLY) 바로 mock 반환
 * - 서버 주소가 있으면 실제 요청을 시도하고, 실패하면 경고 로그 + mock 반환
 *
 * @param {() => Promise<any>} fetchFn   실제 API 호출 함수
 * @param {any} mockData                 실패/미설정 시 사용할 mock 데이터
 * @param {string} label                 콘솔 로그용 라벨
 */
export async function withFallback(fetchFn, mockData, label = 'API') {
  if (USE_MOCK_ONLY) {
    await delay(MOCK_DELAY_MS);
    return mockData;
  }
  try {
    return await fetchFn();
  } catch (err) {
    console.warn(`[${label}] 서버 요청 실패 → mock 데이터로 대체합니다.`, err);
    await delay(MOCK_DELAY_MS);
    return mockData;
  }
}
