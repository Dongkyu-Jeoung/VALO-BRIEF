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
    // 상대 프리미어 팀 티어(RP/상위 %)는 백엔드에서 아직 안 내려줌(Henrik API에 대응 데이터
    // 없음) - 나머지 필드가 연동된 뒤에도 티어 박스는 당분간 mock 값으로 채워둔다.
    async () => ({
      tier: quickAnalysisMock.tier,
      ...(await httpClient.get(ENDPOINTS.teamQuickAnalysis(teamName, teamTag))),
    }),
    quickAnalysisMock,
    'fetchQuickAnalysis'
  );
}
