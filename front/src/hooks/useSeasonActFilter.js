import { useState } from 'react';
import { SEASONS, ACTS } from '../constants/seasons';

export function useSeasonActFilter(defaultSeason = SEASONS[0], defaultAct = ACTS[0]) {
  const [season, setSeason] = useState(defaultSeason);
  const [act, setAct] = useState(defaultAct);
  return { season, setSeason, act, setAct, seasons: SEASONS, acts: ACTS };
}
