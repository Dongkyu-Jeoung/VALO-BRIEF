import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { playerProfileMock } from '../mocks/player.mock';
import { episodeToYearLabel, yearLabelToEpisode } from '../utils/episodeYear';

// 백엔드 actOptions는 "Episode 11" 형식(Riot 공식 표기)으로 온다. 화면에는 "2026"처럼
// 연도로 보여주고 싶어서, 여기(API 경계)에서 한 번만 변환해둔다 - 이후 훅/컴포넌트는
// "연도" 라벨만 알면 되고 Episode 표기를 신경 쓸 필요가 없다.
export function fetchPlayerProfile(riotId, tag) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.playerProfile(riotId, tag)),
    playerProfileMock,
    'fetchPlayerProfile'
  ).then((data) => ({
    ...data,
    actOptions: (data.actOptions ?? []).map((o) => ({ ...o, season: episodeToYearLabel(o.season) })),
  }));
}

// ProfileHeader의 시즌/Act 선택박스용. 매치 목록이 아니라 그 구간의 모드별 스탯만 다시 받아온다.
// season은 화면 표시용 연도("2026")로 들어오므로, 백엔드가 기대하는 "Episode 11" 형식으로
// 되돌려서 요청한다.
export function fetchPlayerModeStats(riotId, tag, season, act) {
  return withFallback(
    () => httpClient.get(ENDPOINTS.playerModeStats(riotId, tag, yearLabelToEpisode(season), act)),
    playerProfileMock.modeStats,
    'fetchPlayerModeStats'
  );
}
