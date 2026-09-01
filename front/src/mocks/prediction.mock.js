export const predictionMock = {
  ourTeam: { name: 'Team Phoenix', tag: 'PHX', avgWinRate20: 58 },
  opponentTeam: { name: 'Team Ascend', tag: 'ASC', avgWinRate20: 45 },
  ourWinChance: 64,
  analysis: {
    roundInfo: {
      atkWinRate: 54, defWinRate: 61, pistolWinRate: 70, ecoWinRate: 32,
      fbWinPct: 68, fdLosePct: 74,
    },
    mapInfoByMap: {
      'abyss': {
        mapWinRate: 65, atkWinRate: 52, defWinRate: 61,
        preferredSites: { A: 48, B: 33, center: 19 },
        avgSpikePlantTime: 32,
        matchSample: 13,
        combos: [
          { label: '조합 A', pct: 34, agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'] },
          { label: '조합 B', pct: 21, agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'] },
        ],
        comboAce: [
          { name: 'Nova', acs: 274 },
          { name: 'Dash', acs: 235 },
        ],
        comboWeakness: [
          { name: 'Ruko', fd: 61, acs: 196 },
          { name: 'Solstice', fd: 58, acs: 180 },
        ],
      },
      'ascent': {
        mapWinRate: 70, atkWinRate: 52, defWinRate: 65,
        preferredSites: { A: 48, B: 33, center: 19 },
        avgSpikePlantTime: 32,
        matchSample: 13,
        combos: [
          { label: '조합 A', pct: 34, agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'] },
          { label: '조합 B', pct: 21, agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'] },
        ],
        comboAce: [
          { name: 'Nova', acs: 274 },
          { name: 'Dash', acs: 235 },
        ],
        comboWeakness: [
          { name: 'Ruko', fd: 61, acs: 196 },
          { name: 'Solstice', fd: 58, acs: 180 },
        ],
      },
      'bind': {
        mapWinRate: 55, atkWinRate: 48, defWinRate: 61,
        preferredSites: { A: 41, B: 40, center: 19 },
        avgSpikePlantTime: 35,
        matchSample: 11,
        combos: [
          { label: '조합 A', pct: 29, agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'] },
          { label: '조합 B', pct: 18, agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'] },
        ],
        comboAce: [
          { name: 'Dash', acs: 251 },
          { name: 'Iris', acs: 219 },
        ],
        comboWeakness: [
          { name: 'Solstice', fd: 55, acs: 171 },
          { name: 'Ruko', fd: 49, acs: 165 },
        ],
      },
    },
    engagementInfo: {
      trade1v1: 58, trade1v2: 31,
      skills: [
        { name: '연막', engageRate: 32, successRate: 51 },
        { name: '플래시', engageRate: 28, successRate: 44 },
        { name: '감시 카메라', engageRate: 19, successRate: 62 },
      ],
      duelistVsDuelist: { us: 58, them: 42 },
      sentinelCompare: 'advantage',
    },
  },
  aiReport: {
    intro: 'Team Ascend는 최근 5경기 기준 3승 2패를 기록 중입니다.',
    strengths: ['피스톨 라운드 승률 높음'],
    weaknesses: ['Eco 라운드 취약'],
    tactic: '초반 공략 집중',
    phases: [{ label: 'EARLY', text: '빠른 압박 주의' }],
    opponentPickAnalysisText: '듀얼리스트 조합 선호',
  },
};