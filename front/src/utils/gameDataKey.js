import { gameData } from '../constants/gameData';

function buildIndex(list) {
  const map = new Map();
  for (const item of list) map.set(item.name, item.id);
  return map;
}

const agentIndex = buildIndex(gameData.agents);
const mapIndex = buildIndex(gameData.maps);
const tierIndex = buildIndex(gameData.tiers.personal);
const teamTierIds = new Set(gameData.tiers.team.map((t) => t.id));

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

// 프리미어 디비전 번호 -> 팀 등급 아이콘(gameData.tiers.team) 변환.
// 라이엇 공식 안내(Premier 문서/위키)에 따르면 Open→Intermediate→Advanced→Elite는 각각
// 5단계씩이고 그 위에 Contender, 최상위 Invite가 있다(지역 인원수에 따라 단계 수가 줄어들
// 수 있다고도 안내됨). Henrik이 주는 division은 이 6개 등급을 관통하는 연속된 정수라
// 정확한 지역별 경계값이 공식적으로 숫자로 문서화돼 있진 않지만, "5단계 구조"와 실제 관찰된
// 최상위 디비전(주요 지역 기준 22)을 근거로 아래 경계값을 추정해 매핑한다 - 지역/시기에 따라
// 실제와 다를 수 있음(4-1 참고, team_search.md).
export function teamTierKey(division) {
  const num = typeof division === 'number'
    ? division
    : parseInt(String(division ?? '').replace(/[^0-9]/g, ''), 10);
  if (!Number.isFinite(num) || num <= 0) return null;

  let id;
  if (num <= 5) id = 'open';
  else if (num <= 10) id = 'intermediate';
  else if (num <= 15) id = 'advanced';
  else if (num <= 20) id = 'elite';
  else if (num === 21) id = 'contender';
  else id = 'invite';

  return teamTierIds.has(id) ? id : null;
}
