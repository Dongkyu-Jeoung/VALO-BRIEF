import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';

// 데모/QA용: 이름에 'nope'가 포함되면 존재하지 않는 것으로 응답합니다.
export function checkPlayerExists(riotId, tag) {
  const exists = !riotId.toLowerCase().includes('nope');
  return withFallback(
    () => httpClient.get(ENDPOINTS.checkPlayerExists(riotId, tag)),
    { exists, riotId, tag },
    'checkPlayerExists'
  );
}

export function checkTeamExists(teamName, teamTag) {
  const exists = !teamName.toLowerCase().includes('nope');
  return withFallback(
    () => httpClient.get(ENDPOINTS.checkTeamExists(teamName, teamTag)),
    { exists, teamName, teamTag },
    'checkTeamExists'
  );
}
