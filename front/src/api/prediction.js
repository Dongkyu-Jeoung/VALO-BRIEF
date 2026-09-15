import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { FORCE_MOCK_PREDICTION, MOCK_DELAY_MS } from './config';
import { predictionMock } from '../mocks/prediction.mock';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../constants/demoTeam';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// DEMO_TEAM(team-ascend#ASC)은 실제로 존재하지 않는 프리미어 팀이라 백엔드가 항상
// 404를 낸다 - api/teams.js의 동일 목적 헬퍼와 같은 이유로 여기서도 네트워크를 아예
// 안 타고 mock으로 바로 응답한다(2026-09-14).
function _isDemoTeam(teamName, teamTag) {
  return (teamName || '').trim().toLowerCase() === DEMO_TEAM_NAME
    && (teamTag || '').trim().toLowerCase() === DEMO_TEAM_TAG.toLowerCase();
}

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
  if (FORCE_MOCK_PREDICTION || _isDemoTeam(teamName, teamTag)) {
    return delay(MOCK_DELAY_MS).then(() => predictionMock);
  }

  return withFallback(
    // 라운드/맵별 상세 분석(analysis)은 이 응답이 아니라 fetchTeamAnalysis가 따로 채운다
    // (teams.js). AI 리포트(aiReport)도 이제 fetchTeamAiReport로 따로 받아온다(teams.js
    // 참고, services/opponent_ai_report.py) - 여기서는 더 이상 mock으로 덮어쓰지 않는다.
    async () => ({
      analysis: predictionMock.analysis,
      ...(await httpClient.get(ENDPOINTS.prediction(teamName, teamTag))),
    }),
    predictionMock,
    'fetchPrediction',
    // 422(입력값 오류, 예: 팀을 못 찾음)뿐 아니라 5xx(모델 파일 없음, LLM 호출 실패 등
    // 실제 서버 장애)도 mock으로 조용히 대체하지 않고 그대로 재던진다(2026-09-15) -
    // 예전엔 422만 재던지고 나머지는 전부 mock으로 덮어써서, 백엔드가 진짜 장애
    // 상태(모델 미존재 등)일 때도 사용자에게는 정상 예측 결과처럼 보이는 문제가 있었다.
    // 5xx를 재던지면 MatchPredictionPage.jsx의 predictionError 처리(이미 구현돼 있음)가
    // 동작해서 "승부예측을 진행할 수 없습니다" 같은 명확한 안내가 사용자에게 표시된다.
    (err) => {
      const match = err.message?.match(/^\[HTTP (\d+)\]/);
      const status = match ? Number(match[1]) : null;
      return status === 422 || (status !== null && status >= 500);
    }
  );
}