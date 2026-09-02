import { gameData } from '../constants/gameData';

function buildIndex(list) {
  const map = new Map();
  for (const item of list) map.set(item.name, item.id);
  return map;
}

const agentIndex = buildIndex(gameData.agents);
const mapIndex = buildIndex(gameData.maps);
const tierIndex = buildIndex(gameData.tiers.personal);

export function agentKey(nameKo) {
  return agentIndex.get(nameKo) ?? null;
}

export function mapKey(nameKo) {
  return mapIndex.get(nameKo) ?? null;
}

export function tierKey(nameKo) {
  if (!nameKo) return null;
  if (tierIndex.has(nameKo)) return tierIndex.get(nameKo);
  // "플래티넘 3 50"처럼 RR이 뒤에 붙어 오는 경우 마지막 토큰만 떼고 한 번 더 조회
  const lastSpace = nameKo.lastIndexOf(' ');
  return lastSpace === -1 ? null : tierIndex.get(nameKo.slice(0, lastSpace)) ?? null;
}
