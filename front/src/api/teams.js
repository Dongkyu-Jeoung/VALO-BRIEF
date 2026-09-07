import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { teamProfileMock, quickAnalysisMock } from '../mocks/team.mock';

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
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}/analysis`),
    teamProfileMock,
    'fetchTeamAnalysis'
  );
}