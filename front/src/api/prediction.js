import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { FORCE_MOCK_PREDICTION, MOCK_DELAY_MS } from './config';
import { predictionMock } from '../mocks/prediction.mock';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 로그인한 팀의 가장 최근 프리미어 매치 상대팀 조회 (/api/predict/recent-opponent).
// 비로그인이거나(401) 최근 매치를 못 찾으면(404) null - 호출부(MatchPredictionPage)가
// null이면 URL의 팀(데모용 mock)을 그대로 쓴다. withFallback을 안 쓰는 이유: 실패가
// "존재하지 않음"이 아니라 "아직 상대팀을 못 정했다"는 정상 상태라 mock으로 대체할
// 필요 없이 그냥 null로 알려주면 된다.
export async function fetchRecentOpponent() {
  try {
    return await httpClient.get('/api/predict/recent-opponent');
  } catch {
    return null;
  }
}

export function fetchPrediction(teamName, teamTag) {
  // FORCE_MOCK_PREDICTION(config.js) - 승부예측 ML 파이프라인이 너무 느려서 백엔드
  // 성능 개선 전까지 임시로 항상 mock을 쓴다(config.js 주석 참고).
  if (FORCE_MOCK_PREDICTION) return delay(MOCK_DELAY_MS).then(() => predictionMock);

  return withFallback(
    // 라운드/맵별 상세 분석(analysis)·AI 리포트(aiReport)는 백엔드 모델이 아직 만들지
    // 않는 데이터라 당분간 mock으로 채운다 - 승률(ourWinChance)/팀 요약만 실제 값.
    async () => ({
      analysis: predictionMock.analysis,
      aiReport: predictionMock.aiReport,
      ...(await httpClient.get(ENDPOINTS.prediction(teamName, teamTag))),
    }),
    predictionMock,
    'fetchPrediction'
  );
}
