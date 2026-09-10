export const predictionMock = {
  ourTeam: { name: 'Team Phoenix', tag: 'PHX', avgWinRate20: 58, logoUrl: null },
  opponentTeam: { name: 'Team Ascend', tag: 'ASC', avgWinRate20: 45, logoUrl: null },
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
          { agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'], result: 'win' },
          { agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'], result: 'lose' },
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
          { agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'], result: 'win' },
          { agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'], result: 'lose' },
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
          { agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'], result: 'win' },
          { agents: ['jett', 'fade', 'viper', 'cypher', 'kayo'], result: 'lose' },
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
      'breeze': {
        mapWinRate: 50, atkWinRate: 45, defWinRate: 55,
        preferredSites: { A: 50, B: 30, center: 20 },
        avgSpikePlantTime: 36,
        matchSample: 8,
        combos: [
          { agents: ['jett', 'sova', 'viper', 'kayo', 'cypher'], result: 'win' },
          { agents: ['neon', 'fade', 'omen', 'killjoy', 'breach'], result: 'lose' },
        ],
        comboAce: [{ name: 'Nova', acs: 260 }],
        comboWeakness: [{ name: 'Ruko', fd: 50, acs: 170 }],
      },
      'haven': {
        mapWinRate: 58, atkWinRate: 50, defWinRate: 58,
        preferredSites: { A: 33, B: 33, center: 34 },
        avgSpikePlantTime: 33,
        matchSample: 12,
        combos: [
          { agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'], result: 'win' },
          { agents: ['raze', 'fade', 'viper', 'cypher', 'skye'], result: 'lose' },
        ],
        comboAce: [{ name: 'Iris', acs: 240 }],
        comboWeakness: [{ name: 'Solstice', fd: 45, acs: 160 }],
      },
      'icebox': {
        mapWinRate: 52, atkWinRate: 49, defWinRate: 53,
        preferredSites: { A: 45, B: 45, center: 10 },
        avgSpikePlantTime: 34,
        matchSample: 9,
        combos: [
          { agents: ['jett', 'sova', 'viper', 'killjoy', 'sage'], result: 'win' },
          { agents: ['reyna', 'fade', 'omen', 'cypher', 'kayo'], result: 'lose' },
        ],
        comboAce: [{ name: 'Dash', acs: 250 }],
        comboWeakness: [{ name: 'Ruko', fd: 52, acs: 175 }],
      },
      'lotus': {
        mapWinRate: 60, atkWinRate: 55, defWinRate: 50,
        preferredSites: { A: 30, B: 40, center: 30 },
        avgSpikePlantTime: 31,
        matchSample: 10,
        combos: [
          { agents: ['raze', 'fade', 'omen', 'viper', 'killjoy'], result: 'win' },
          { agents: ['jett', 'reyna', 'sova', 'cypher', 'breach'], result: 'lose' },
        ],
        comboAce: [{ name: 'Nova', acs: 265 }],
        comboWeakness: [{ name: 'Solstice', fd: 48, acs: 165 }],
      },
      'pearl': {
        mapWinRate: 48, atkWinRate: 42, defWinRate: 54,
        preferredSites: { A: 40, B: 40, center: 20 },
        avgSpikePlantTime: 37,
        matchSample: 7,
        combos: [
          { agents: ['jett', 'fade', 'viper', 'killjoy', 'astra'], result: 'win' },
          { agents: ['reyna', 'sova', 'omen', 'cypher', 'kayo'], result: 'lose' },
        ],
        comboAce: [{ name: 'Iris', acs: 230 }],
        comboWeakness: [{ name: 'Ruko', fd: 55, acs: 160 }],
      },
      'split': {
        mapWinRate: 66, atkWinRate: 58, defWinRate: 60,
        preferredSites: { A: 55, B: 26, center: 19 },
        avgSpikePlantTime: 30,
        matchSample: 9,
        combos: [
          { agents: ['raze', 'omen', 'viper', 'killjoy', 'skye'], result: 'win' },
          { agents: ['jett', 'reyna', 'sova', 'cypher', 'breach'], result: 'lose' },
        ],
        comboAce: [{ name: 'Nova', acs: 281 }],
        comboWeakness: [{ name: 'Solstice', fd: 60, acs: 188 }],
      },
      'sunset': {
        mapWinRate: 57, atkWinRate: 53, defWinRate: 54,
        preferredSites: { A: 45, B: 35, center: 20 },
        avgSpikePlantTime: 33,
        matchSample: 11,
        combos: [
          { agents: ['raze', 'fade', 'omen', 'cypher', 'breach'], result: 'win' },
          { agents: ['jett', 'reyna', 'viper', 'killjoy', 'skye'], result: 'lose' },
        ],
        comboAce: [{ name: 'Dash', acs: 245 }],
        comboWeakness: [{ name: 'Ruko', fd: 50, acs: 170 }],
      },
      'corrode': {
        mapWinRate: 55, atkWinRate: 50, defWinRate: 50,
        preferredSites: { A: 33, B: 33, center: 34 },
        avgSpikePlantTime: 32,
        matchSample: 10,
        combos: [
          { agents: ['jett', 'reyna', 'omen', 'sova', 'killjoy'], result: 'win' },
          { agents: ['raze', 'fade', 'viper', 'cypher', 'kayo'], result: 'lose' },
        ],
        comboAce: [{ name: 'Nova', acs: 250 }],
        comboWeakness: [{ name: 'Ruko', fd: 50, acs: 170 }],
      },
      'summit': {
        mapWinRate: 53, atkWinRate: 48, defWinRate: 55,
        preferredSites: { A: 40, B: 40, center: 20 },
        avgSpikePlantTime: 34,
        matchSample: 8,
        combos: [
          { agents: ['jett', 'sova', 'viper', 'killjoy', 'sage'], result: 'win' },
          { agents: ['reyna', 'fade', 'omen', 'cypher', 'kayo'], result: 'lose' },
        ],
        comboAce: [{ name: 'Iris', acs: 240 }],
        comboWeakness: [{ name: 'Solstice', fd: 48, acs: 165 }],
      },
      'fracture': {
        mapWinRate: 56, atkWinRate: 52, defWinRate: 48,
        preferredSites: { A: 35, B: 35, center: 30 },
        avgSpikePlantTime: 31,
        matchSample: 12,
        combos: [
          { agents: ['raze', 'breach', 'omen', 'killjoy', 'viper'], result: 'win' },
          { agents: ['jett', 'fade', 'sova', 'cypher', 'kayo'], result: 'lose' },
        ],
        comboAce: [{ name: 'Dash', acs: 260 }],
        comboWeakness: [{ name: 'Ruko', fd: 52, acs: 180 }],
      },
    },
    // 우리팀 분석 화면(EngagementInfoBlock, MyTeamAnalysisPage) 전용 - 실측 통계 mock.
    // skills 서브 항목은 폐기 결정(server/승부예측_성능_분석.md 6-1번 참고)이라 새 필드
    // (engagementPrediction, 아래)에는 안 넣었지만, 우리팀 분석 쪽 mock은 기존 컴포넌트가
    // 그대로 참조하므로 남겨둔다.
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
    // 상대팀 검색(승부예측) 분석 탭 ③번 전용 - AI 모델 예측 결과 mock.
    // components/analysis/EngagementPredictionBlock.jsx가 기대하는 shape 그대로
    // (server/승부예측_성능_분석.md 7번의 API 계약과 동일) - 실제 모델이 만들어지면
    // routers/teams.py::get_team_analysis가 이 shape으로 engagementPrediction을 채워야 함.
    engagementPrediction: {
      trade: { ourWinRate: 62, theirWinRate: 38 },
      duelistMatchup: { ourScore: 58, theirScore: 42, favor: 'us' },
      modelVersion: 'engagement-v1 (mock)',
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