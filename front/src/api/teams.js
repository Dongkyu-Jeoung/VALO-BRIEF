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