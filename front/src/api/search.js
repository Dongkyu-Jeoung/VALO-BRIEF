import { httpClient } from "./httpClient";
import { ENDPOINTS } from "./endpoints";
import { USE_MOCK_ONLY, MOCK_DELAY_MS } from "./config";

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 백엔드 자체가 없는 개발 초기(USE_MOCK_ONLY)에는 데모 편의상 'nope' 포함 여부로만 판단한다.

// 데모/QA용: 이름에 'nope'가 포함되면 존재하지 않는 것으로 응답합니다.
export function checkPlayerExists(riotId, tag) {
  if (USE_MOCK_ONLY) {
    const exists = !riotId.toLowerCase().includes("nope");
    return delay(MOCK_DELAY_MS).then(() => ({ exists, riotId, tag }));
  }
  return httpClient.get(ENDPOINTS.checkPlayerExists(riotId, tag));
}

export function checkTeamExists(teamName, teamTag) {
  if (USE_MOCK_ONLY) {
    const exists = !teamName.toLowerCase().includes("nope");
    return delay(MOCK_DELAY_MS).then(() => ({ exists, teamName, teamTag }));
  }
  return httpClient.get(ENDPOINTS.checkTeamExists(teamName, teamTag));
}
