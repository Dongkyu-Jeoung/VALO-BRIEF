import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { withFallback } from './withFallback';
import { MOCK_DELAY_MS } from './config';
import { teamProfileMock, quickAnalysisMock } from '../mocks/team.mock';
import { predictionMock } from '../mocks/prediction.mock';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../constants/demoTeam';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// DEMO_TEAM(team-ascend#ASC)은 실제로 존재하지 않는 프리미어 팀이라 백엔드가 항상
// 404를 낸다(withFallback이 잡아서 어차피 mock으로 대체하지만, 그 전에 뻔한 404
// 요청이 매번 나가는 게 문제였다 - 2026-09-14). 이 값이면 아래 함수들 모두 네트워크를
// 아예 타지 않고 바로 mock을 반환한다.
function _isDemoTeam(teamName, teamTag) {
  return (teamName || '').trim().toLowerCase() === DEMO_TEAM_NAME
    && (teamTag || '').trim().toLowerCase() === DEMO_TEAM_TAG.toLowerCase();
}

export function fetchTeamProfile(teamName, teamTag) {
  if (_isDemoTeam(teamName, teamTag)) return delay(MOCK_DELAY_MS).then(() => teamProfileMock);
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}`),
    teamProfileMock,
    'fetchTeamProfile'
  );
}

// 성능 개선: 팀 로고/이름/디비전 등 ProfileHeader에 필요한 부분만 빠르게 받아오는 경량
// 요청. fetchTeamProfile(매치 이력까지 포함, 느림)과 별도로 먼저 호출해서 헤더부터 그리고,
// 나머지는 fetchTeamProfile이 도착하는 대로 채운다 (TeamProfilePage 참고). mock은
// teamProfileMock을 그대로 재사용해도 필요한 필드가 다 있어 문제없다.
export function fetchTeamHeader(teamName, teamTag) {
  if (_isDemoTeam(teamName, teamTag)) return delay(MOCK_DELAY_MS).then(() => teamProfileMock);
  return withFallback(
    () => httpClient.get(ENDPOINTS.teamHeader(teamName, teamTag)),
    teamProfileMock,
    'fetchTeamHeader'
  );
}

export function fetchQuickAnalysis(teamName, teamTag) {
  // "3초 상대분석 리포트"(QuickAnalysisModal) 팝업이 데모 팀으로 열릴 때 이 경로를 탄다.
  // HomePage가 initialData로 첫 fetch는 건너뛰게 해뒀지만, React.StrictMode(main.jsx)의
  // 개발 모드 effect 이중 실행 때문에 skipNextFetch 가드가 두 번째 실행에서는 이미
  // 소진돼(ref라 리셋 안 됨) 결국 한 번은 실제로 이 함수가 호출돼 404가 났다(2026-09-14
  // 실측: "GET /api/teams/team-ascend/ASC/quick-analysis" 404). 근본 원인(StrictMode
  // 이중 호출)을 직접 고치는 대신, 다른 데모 팀 함수들과 동일하게 여기서도 네트워크
  // 자체를 안 타게 막는 게 더 견고하다 - 몇 번 호출되든 상관없이 항상 안전해진다.
  if (_isDemoTeam(teamName, teamTag)) return delay(MOCK_DELAY_MS).then(() => quickAnalysisMock);
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    async () => ({
      tier: quickAnalysisMock.tier,
      ...(await httpClient.get(`/api/teams/${cleanName}/${cleanTag}/quick-analysis`)),
    }),
    quickAnalysisMock,
    'fetchQuickAnalysis'
  );
}

export function fetchTeamAnalysis(teamName, teamTag) {
  if (_isDemoTeam(teamName, teamTag)) return delay(MOCK_DELAY_MS).then(() => predictionMock.analysis);
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}/analysis`),
    // teamProfileMock이 아니라 predictionMock.analysis를 써야 한다 - MatchPredictionPage가
    // 기대하는 roundInfo/mapInfoByMap 등은 teamProfileMock엔 아예 없어서(팀 프로필 전용
    // mock) 예전엔 실패 시 roundInfo가 통째로 빈 값(0)이 되던 버그였다.
    predictionMock.analysis,
    'fetchTeamAnalysis'
  );
}

// 승부예측 "AI 리포트" 탭(상대팀 인사이트) - Claude 생성이 20~45초 걸려(services/
// opponent_ai_report.py 참고) 백엔드가 그 자리에서 기다리지 않고 항상 빠르게
// { status: "ready", report } | { status: "not_ready" } | { status: "generating" }
// 셋 중 하나로 즉시 응답한다. status가 없을 이유가 없지만(백엔드 계약), 방어적으로
// data?.status로 접근한다. withFallback은 실제로 던져진 예외에만 mock으로 대체하므로
// 정상 status 값들은 그대로 통과한다 - MatchPredictionPage/index.jsx가 "generating"이면
// 잠시 후 다시 이 함수를 호출해 폴링한다.
export function fetchTeamAiReport(teamName, teamTag) {
  if (_isDemoTeam(teamName, teamTag)) {
    return delay(MOCK_DELAY_MS).then(() => ({ status: 'ready', report: predictionMock.aiReport }));
  }
  const cleanName = encodeURIComponent((teamName || '').trim());
  const cleanTag = encodeURIComponent((teamTag || '').trim());
  return withFallback(
    () => httpClient.get(`/api/teams/${cleanName}/${cleanTag}/ai-report`),
    { status: 'ready', report: predictionMock.aiReport },
    'fetchTeamAiReport'
  );
}