import { useEffect, useState } from 'react';
import { SEASONS, ACTS } from '../constants/seasons';

/**
 * actOptions: 백엔드가 실제 데이터 기준으로 내려주는 [{ season, acts: [...] }, ...] (최신순).
 * 넘기지 않으면(팀 프로필처럼 아직 백엔드 연동이 없는 화면) 기존 고정 SEASONS/ACTS로 동작합니다.
 * 넘기면 seasons/acts 옵션과 기본 선택값이 실제 데이터가 있는 최신 시즌/Act로 맞춰지고,
 * 시즌을 바꾸면 act도 그 시즌의 최신 Act로 자동 리셋됩니다(존재하지 않는 조합 방지).
 */
export function useSeasonActFilter(actOptions) {
  const hasDynamic = Array.isArray(actOptions) && actOptions.length > 0;
  const seasons = hasDynamic ? actOptions.map((o) => o.season) : SEASONS;
  const actsFor = (s) => (hasDynamic ? actOptions.find((o) => o.season === s)?.acts ?? [] : ACTS);

  const [season, setSeasonState] = useState(seasons[0]);
  const [act, setAct] = useState(actsFor(seasons[0])[0]);

  // actOptions가 비동기로(프로필 로드 후) 도착하면 그 시점의 최신 시즌/Act로 다시 맞춘다
  useEffect(() => {
    if (!hasDynamic) return;
    setSeasonState(seasons[0]);
    setAct(actsFor(seasons[0])[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actOptions]);

  function setSeason(newSeason) {
    setSeasonState(newSeason);
    setAct(actsFor(newSeason)[0]);
  }

  return { season, setSeason, act, setAct, seasons, acts: actsFor(season) };
}
