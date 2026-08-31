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
