// ============================================================
// FastAPI 서버에 맞춘 엔드포인트 경로 모음
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
  playerModeStats: (riotId, tag, season, act) =>
    `/api/players/${encodeURIComponent(riotId)}/${encodeURIComponent(tag)}/mode-stats?season=${encodeURIComponent(season)}&act=${encodeURIComponent(act)}`,

  // 상대팀 전적 검색 (Frame 06) + 3초 상대분석 팝업 (Frame 05)
  teamProfile: (teamName, teamTag) => `/api/teams/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}`,
  teamQuickAnalysis: (teamName, teamTag) => `/api/teams/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}/quick-analysis`,

  // [추가] 상대 팀 분석 및 승부 예측 탭 전용 엔드포인트 (백엔드 teams.py /analysis와 연동)
  teamAnalysis: (teamName, teamTag) => `/api/teams/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}/analysis`,

  // 승부 예측 (기존 유지)
  prediction: (teamName, teamTag) => `/api/predict/${encodeURIComponent(teamName)}/${encodeURIComponent(teamTag)}`,

  // 우리팀 분석 (Frame 09~13, 로그인 필요)
  myTeamStats: () => `/api/my-team/stats`,
  myTeamPlayers: () => `/api/my-team/players`,
  myTeamPlayerDetail: (playerId) => `/api/my-team/players/${encodeURIComponent(playerId)}`,
  myTeamAnalysis: () => `/api/my-team/analysis`,
  myTeamAiReport: () => `/api/my-team/ai-report`,
};