export const teamProfileMock = {
  name: 'Team Ascend',
  tag: 'ASC',
  division: '디비전 2',
  ratingIconUrl: null,
  recentSummary: { winRate: 65, wins: 13, losses: 7, avgRoundWin: 13, avgRoundLose: 8 },
  playerRanking: [
    { rank: 1, name: 'Nova', acs: 274, hs: 28, position: '타격대', kd: 1.5 },
    { rank: 2, name: 'Dash', acs: 235, hs: 22, position: '척후대', kd: 1.2 },
    { rank: 3, name: 'Iris', acs: 210, hs: 19, position: '감시자', kd: 1.0 },
    { rank: 4, name: 'Ruko', acs: 196, hs: 17, position: '전략가', kd: 0.9 },
    { rank: 5, name: 'Solstice', acs: 180, hs: 15, position: '타격대', kd: 0.8 },
  ],
  mapWinrates: [
    { map: '어센트', win: 13, lose: 8, winRate: 70 },
    { map: '바인드', win: 12, lose: 10, winRate: 55 },
    { map: '헤이븐', win: 10, lose: 11, winRate: 42 },
  ],
  matchHistory: [
    { map: '어센트', result: 'win', date: '08.24', time: '9:48 AM', roundScore: '13-7', kda: 2.4, adr: 172, acs: 248, firstBlood: 9, mvp: { agent: 'Jett', player: 'Nova', kda: 3.1, hs: 31, acs: 302 }, season: 'S2026', act: 'Act 2' },
    { map: '바인드', result: 'lose', date: '08.23', time: '8:10 PM', roundScore: '9-13', kda: 1.5, adr: 134, acs: 190, firstBlood: 4, mvp: { agent: 'Reyna', player: 'Dash', kda: 1.9, hs: 24, acs: 224 }, season: 'S2026', act: 'Act 2' },
    { map: '헤이븐', result: 'win', date: '08.23', time: '6:30 PM', roundScore: '13-11', kda: 2.1, adr: 158, acs: 226, firstBlood: 7, mvp: { agent: 'Omen', player: 'Iris', kda: 2.6, hs: 20, acs: 251 }, season: 'S2026', act: 'Act 1' },
    { map: '스플릿', result: 'win', date: '08.22', time: '9:00 PM', roundScore: '13-6', kda: 2.8, adr: 181, acs: 264, firstBlood: 10, mvp: { agent: 'Jett', player: 'Nova', kda: 3.4, hs: 33, acs: 310 }, season: 'S2026', act: 'Act 1' },
    { map: '로터스', result: 'lose', date: '08.22', time: '6:45 PM', roundScore: '8-13', kda: 1.3, adr: 121, acs: 172, firstBlood: 3, mvp: { agent: 'Sova', player: 'Ruko', kda: 1.6, hs: 18, acs: 199 }, season: 'S2025', act: 'Act 3' },
  ],
};

export const quickAnalysisMock = {
  teamName: 'Team Ascend',
  teamTag: 'ASC',
  recentForm: ['win', 'win', 'lose', 'win', 'lose'],
  wins: 3, losses: 2, winRate: 60, avgRoundWin: 13, avgRoundLose: 8,
  tier: { division: '디비전 3', rp: 5432, topPercent: 24 },
  playerRanking: [
    { rank: 1, name: 'Zeta', acs: 268, hs: 29, position: '타격대', kd: 1.42, adr: 172 },
    { rank: 2, name: 'Rho', acs: 241, hs: 24, position: '척후대', kd: 1.25, adr: 158 },
    { rank: 3, name: 'Kai', acs: 220, hs: 21, position: '감시자', kd: 1.10, adr: 144 },
    { rank: 4, name: 'Milo', acs: 205, hs: 19, position: '전략가', kd: 1.02, adr: 136 },
    { rank: 5, name: 'Vex', acs: 188, hs: 17, position: '타격대', kd: 0.95, adr: 121 },
  ],
};
