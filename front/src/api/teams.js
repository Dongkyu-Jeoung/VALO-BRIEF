import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { teamProfileMock, quickAnalysisMock } from '../mocks/team.mock';

export function fetchTeamProfile(teamName, teamTag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.teamProfile(teamName, teamTag)),
    teamProfileMock,
    'fetchTeamProfile'
  );
}

export function fetchQuickAnalysis(teamName, teamTag) {
  return withFallback(
    async () => ({
      tier: quickAnalysisMock.tier,
      ...(await httpClient.get(ENDPOINTS.teamQuickAnalysis(teamName, teamTag))),
    }),
    quickAnalysisMock,
    'fetchQuickAnalysis'
  );
}

export function fetchTeamAnalysis(teamName, teamTag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.teamAnalysis(teamName, teamTag)),
    teamProfileMock,
    'fetchTeamAnalysis'
  );
}