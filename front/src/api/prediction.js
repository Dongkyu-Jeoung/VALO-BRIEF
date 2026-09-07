import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { predictionMock } from '../mocks/prediction.mock';

export function fetchPrediction(teamName, teamTag) {
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
