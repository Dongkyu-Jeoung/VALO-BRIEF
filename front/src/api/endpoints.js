// ============================================================
// FastAPI 서버에 맞춘 엔드포인트 경로 모음
// 백엔드 라우터를 이 경로에 맞춰 구현하면 프론트 수정 없이 바로 연동됩니다.
// (경로/파라미터 이름은 자유롭게 바꿔도 되고, 바꾸면 여기 한 곳만 고치면 됩니다)
// ============================================================

export const ENDPOINTS = {
  // 인증
  login: () => `/api/auth/login`,
  signup: () => `/api/auth/signup`,
  verifyRiotId: () => `/api/auth/riot-verify`,
  checkIdAvailable: (id) => `/api/auth/id-available?id=${encodeURIComponent(id)}`,

  // 통합 검색 (메인/헤더 검색창)
  checkPlayerExists: (riotId, tag) => `/api/search/players/${encodeURIComponent(riotId)}/${encodeURIComponent(tag)}/exists`,
  checkTeamExists: (teamName, teamTag) => `/api/search/teams/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}/exists`,

  // 개인 검색 (Frame 04)
  playerProfile: (riotId, tag) => `/api/players/${encodeURIComponent(riotId)}/${encodeURIComponent(tag)}`,

  // 상대팀 전적 검색 (Frame 06) + 3초 상대분석 팝업 (Frame 05)
  teamProfile: (teamName, teamTag) => `/api/teams/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}`,
  teamQuickAnalysis: (teamTag) => `/api/teams/${encodeURIComponent(teamTag)}/quick-analysis`,

  // 승부 예측 (Frame 07, 08)
  prediction: (teamName, teamTag) => `/api/predict/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}`,

  // 우리팀 분석 (Frame 09~13, 로그인 필요)
  myTeamStats: () => `/api/my-team/stats`,
  myTeamPlayers: () => `/api/my-team/players`,
  myTeamPlayerDetail: (playerId) => `/api/my-team/players/${encodeURIComponent(playerId)}`,
  myTeamAnalysis: () => `/api/my-team/analysis`,
  myTeamAiReport: () => `/api/my-team/ai-report`,
};
