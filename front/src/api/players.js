import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { playerProfileMock } from '../mocks/player.mock';

export function fetchPlayerProfile(riotId, tag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.playerProfile(riotId, tag)),
    playerProfileMock,
    'fetchPlayerProfile'
  );
}
