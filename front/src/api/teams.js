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

export function fetchQuickAnalysis(teamTag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.teamQuickAnalysis(teamTag)),
    quickAnalysisMock,
    'fetchQuickAnalysis'
  );
}
