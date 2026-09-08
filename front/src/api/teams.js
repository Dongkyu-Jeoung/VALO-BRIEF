import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { FORCE_MOCK_PREDICTION, MOCK_DELAY_MS } from './config';
import { teamProfileMock, quickAnalysisMock } from '../mocks/team.mock';
import { predictionMock } from '../mocks/prediction.mock';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function fetchTeamProfile(teamName, teamTag) {
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}`),
    teamProfileMock,
    'fetchTeamProfile'
  );
}

// 성능 개선: 팀 로고/이름/디비전 등 ProfileHeader에 필요한 부분만 빠르게 받아오는 경량
// 요청. fetchTeamProfile(매치 이력까지 포함, 느림)과 별도로 먼저 호출해서 헤더부터 그리고,
// 나머지는 fetchTeamProfile이 도착하는 대로 채운다 (TeamProfilePage 참고). mock은
// teamProfileMock을 그대로 재사용해도 필요한 필드가 다 있어 문제없다.
export function fetchTeamHeader(teamName, teamTag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.teamHeader(teamName, teamTag)),
    teamProfileMock,
    'fetchTeamHeader'
  );
}

export function fetchQuickAnalysis(teamName, teamTag) {
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    async () => ({
      tier: quickAnalysisMock.tier,
      ...(await httpClient.get(`/api/teams/${cleanName}/${cleanTag}/quick-analysis`)),
    }),
    quickAnalysisMock,
    'fetchQuickAnalysis'
  );
}

export function fetchTeamAnalysis(teamName, teamTag) {
  // FORCE_MOCK_PREDICTION(config.js) - 승부예측 페이지 전용 호출이라 백엔드 성능 개선
  // 전까지 임시로 항상 mock을 쓴다.
  if (FORCE_MOCK_PREDICTION) return delay(MOCK_DELAY_MS).then(() => predictionMock.analysis);

  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}/analysis`),
    // teamProfileMock이 아니라 predictionMock.analysis를 써야 한다 - MatchPredictionPage가
    // 기대하는 roundInfo/mapInfoByMap 등은 teamProfileMock엔 아예 없어서(팀 프로필 전용
    // mock) 예전엔 실패 시 roundInfo가 통째로 빈 값(0)이 되던 버그였다.
    predictionMock.analysis,
    'fetchTeamAnalysis'
  );
}