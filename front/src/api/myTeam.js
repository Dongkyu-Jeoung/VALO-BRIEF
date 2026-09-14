import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import {
  myTeamStatsMock,
  myTeamPlayersMock,
  myTeamPlayerDetailMock,
  myTeamAnalysisMock,
  myTeamAiReportMock,
} from '../mocks/myTeam.mock';

export function fetchMyTeamStats() {
  return withFallback(
    () => httpClient.get(ENDPOINTS.myTeamStats()),
    myTeamStatsMock,
    'fetchMyTeamStats'
  );
}

export function fetchMyTeamPlayers() {
  return withFallback(
    () => httpClient.get(ENDPOINTS.myTeamPlayers()),
    myTeamPlayersMock,
    'fetchMyTeamPlayers'
  );
}

// 헤더/메뉴바 "개인 검색" 전용(useResolvedNavLinks.js::goToPersonalSearch) - 로스터 중
// ACS 최고이면서 지금도 Henrik에서 실제로 조회되는 선수를 서버가 골라서 내려준다
// (services/my_team_players.py::resolve_personal_search_target 참고, Riot ID를 바꾼
// 선수로 이동해 빈 프로필이 뜨는 걸 막기 위함). 대상을 못 찾으면(404) null - api/prediction.js::
// fetchRecentOpponent와 동일하게 mock 폴백 없이 그냥 null로 알려주면 호출부가 데모 링크로
// 대체한다.
export async function fetchPersonalSearchTarget() {
  try {
    return await httpClient.get(ENDPOINTS.myTeamSearchTarget());
  } catch {
    return null;
  }
}

export function fetchMyTeamPlayerDetail(playerId) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.myTeamPlayerDetail(playerId)),
    myTeamPlayerDetailMock[playerId] ?? Object.values(myTeamPlayerDetailMock)[0],
    'fetchMyTeamPlayerDetail'
  );
}

export function fetchMyTeamAnalysis() {
  return withFallback(
    () => httpClient.get(ENDPOINTS.myTeamAnalysis()),
    myTeamAnalysisMock,
    'fetchMyTeamAnalysis'
  );
}

export function fetchMyTeamAiReport() {
  return withFallback(
    () => httpClient.get(ENDPOINTS.myTeamAiReport()),
    myTeamAiReportMock,
    'fetchMyTeamAiReport'
  );
}
