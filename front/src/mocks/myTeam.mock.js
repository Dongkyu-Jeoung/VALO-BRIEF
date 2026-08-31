export const myTeamProfileMock = {
  name: 'Team Phoenix',
  tag: 'PHX',
  division: '디비전 2',
  ratingIconUrl: null,
};

export const myTeamStatsMock = {
  recentSummary: { winRate: 65, wins: 13, losses: 7, avgRoundWin: 13, avgRoundLose: 8 },
  playerRanking: [
    { rank: 1, name: 'Zeta', acs: 268, hs: 29, position: '타격대', kd: 1.42 },
    { rank: 2, name: 'Rho', acs: 241, hs: 24, position: '척후대', kd: 1.25 },
    { rank: 3, name: 'Kai', acs: 220, hs: 21, position: '감시자', kd: 1.10 },
    { rank: 4, name: 'Milo', acs: 205, hs: 19, position: '전략가', kd: 1.02 },
    { rank: 5, name: 'Vex', acs: 188, hs: 17, position: '타격대', kd: 0.95 },
  ],
  mapWinrates: [
    { map: '어센트', win: 13, lose: 8, winRate: 70 },
    { map: '바인드', win: 12, lose: 10, winRate: 55 },
    { map: '헤이븐', win: 10, lose: 11, winRate: 42 },
  ],
  matchHistory: [
    { map: '어센트', result: 'win', date: '08.24', time: '9:48 AM', roundScore: '13-7', kda: 2.4, adr: 172, acs: 248, firstBlood: 9, mvp: { agent: 'Jett', player: 'Zeta', kda: 3.1, hs: 31, acs: 302 }, season: 'S2026', act: 'Act 2' },
    { map: '바인드', result: 'lose', date: '08.23', time: '8:10 PM', roundScore: '9-13', kda: 1.5, adr: 134, acs: 190, firstBlood: 4, mvp: { agent: 'Reyna', player: 'Rho', kda: 1.9, hs: 24, acs: 224 }, season: 'S2026', act: 'Act 2' },
    { map: '헤이븐', result: 'win', date: '08.20', time: '7:15 PM', roundScore: '13-9', kda: 2.0, adr: 155, acs: 219, firstBlood: 6, mvp: { agent: 'Omen', player: 'Kai', kda: 2.3, hs: 20, acs: 236 }, season: 'S2026', act: 'Act 1' },
    { map: '스플릿', result: 'lose', date: '07.28', time: '6:40 PM', roundScore: '10-13', kda: 1.4, adr: 129, acs: 176, firstBlood: 3, mvp: { agent: 'Sova', player: 'Milo', kda: 1.7, hs: 19, acs: 198 }, season: 'S2025', act: 'Act 3' },
  ],
};

export const myTeamPlayersMock = [
  { id: 'vex', name: 'Vex', tag: 'PHX', role: '타격대', mostAgent: '제트', kd: 0.95, hs: 17, adr: 121, acs: 188 },
  { id: 'milo', name: 'Milo', tag: 'PHX', role: '전략가', mostAgent: '오멘', kd: 1.02, hs: 19, adr: 136, acs: 205 },
  { id: 'kai', name: 'Kai', tag: 'PHX', role: '감시자', mostAgent: '킬조이', kd: 1.10, hs: 21, adr: 144, acs: 220 },
  { id: 'rho', name: 'Rho', tag: 'PHX', role: '척후대', mostAgent: '소바', kd: 1.25, hs: 24, adr: 158, acs: 241 },
  { id: 'zeta', name: 'Zeta', tag: 'PHX', role: '타격대', mostAgent: '레이나', kd: 1.42, hs: 29, adr: 172, acs: 268 },
];

export const myTeamPlayerDetailMock = {
  zeta: {
    id: 'zeta', name: 'Zeta', tag: 'PHX',
    // 맵별로 나눠 관리 ('전체 맵'은 전체 평균). 실제 연동 시 맵 쿼리로 서버가 내려주면 됩니다.
    roundInfoByMap: {
      '전체 맵': {
        atkKd: 1.5, atkAcs: 255, defKd: 1.3, defAcs: 228,
        fbPct: 21, fdPct: 9,
        pistolKd: 1.8, pistolAcs: 241, ecoKd: 1.1, ecoAcs: 195,
      },
      '어센트': {
        atkKd: 1.6, atkAcs: 261, defKd: 1.4, defAcs: 233,
        fbPct: 23, fdPct: 8,
        pistolKd: 1.9, pistolAcs: 248, ecoKd: 1.2, ecoAcs: 201,
      },
      '바인드': {
        atkKd: 1.3, atkAcs: 239, defKd: 1.2, defAcs: 214,
        fbPct: 18, fdPct: 11,
        pistolKd: 1.6, pistolAcs: 222, ecoKd: 1.0, ecoAcs: 180,
      },
      '헤이븐': {
        atkKd: 1.4, atkAcs: 248, defKd: 1.3, defAcs: 221,
        fbPct: 20, fdPct: 10,
        pistolKd: 1.7, pistolAcs: 235, ecoKd: 1.1, ecoAcs: 190,
      },
      '스플릿': {
        atkKd: 1.7, atkAcs: 270, defKd: 1.5, defAcs: 242,
        fbPct: 25, fdPct: 7,
        pistolKd: 2.0, pistolAcs: 256, ecoKd: 1.3, ecoAcs: 210,
      },
      '로터스': {
        atkKd: 1.2, atkAcs: 231, defKd: 1.1, defAcs: 206,
        fbPct: 16, fdPct: 13,
        pistolKd: 1.5, pistolAcs: 215, ecoKd: 0.9, ecoAcs: 172,
      },
    },
    aim: {
      hitzones: [
        { zone: '헤드', pct: 29 },
        { zone: '바디', pct: 58 },
        { zone: '레그', pct: 13 },
      ],
      weapons: [
        { name: 'Vandal', kd: 1.6, adr: 178 },
        { name: 'Phantom', kd: 1.3, adr: 152 },
        { name: 'Sheriff', kd: 1.1, adr: 98 },
      ],
      clutch: { '1v1': 62, '1v2': 28, '1v3plus': 8 },
    },
    engagement: {
      trade1v1: 55, trade1v2: 24,
      skills: [
        { name: '플래시', engageRate: 34, successRate: 52 },
        { name: '부메랑 탄', engageRate: 26, successRate: 41 },
        { name: '궁극기', engageRate: 18, successRate: 67 },
      ],
      duelistCompare: { me: 58, opponent: 42 },
      distanceDistribution: [
        { x: '0-5m', y: 22 },
        { x: '5-10m', y: 38 },
        { x: '10-15m', y: 27 },
        { x: '15-20m', y: 14 },
        { x: '20m+', y: 6 },
      ],
    },
  },
};

export const myTeamAnalysisMock = {
  roundInfo: {
    atkWinRate: 58, defWinRate: 63, pistolWinRate: 65, ecoWinRate: 38,
    fbWinPct: 71, fdLosePct: 62,
  },
  // 맵별로 키를 나눠 관리합니다 (prediction.mock.js의 mapInfoByMap과 동일한 구조).
  mapInfoByMap: {
    '어센트': {
      mapWinRate: 70, atkWinRate: 56, defWinRate: 68,
      preferredSites: { A: 52, B: 30, center: 18 },
      avgSpikePlantTime: 29,
      matchSample: 13,
      combos: [
        { label: '조합 A', pct: 38 },
        { label: '조합 B', pct: 19 },
      ],
      comboAce: [
        { name: 'Zeta', acs: 268 },
        { name: 'Rho', acs: 241 },
      ],
      comboWeakness: [
        { name: 'Vex', fd: 34, acs: 188 },
        { name: 'Milo', fd: 29, acs: 205 },
      ],
    },
    '바인드': {
      mapWinRate: 55, atkWinRate: 49, defWinRate: 60,
      preferredSites: { A: 40, B: 41, center: 19 },
      avgSpikePlantTime: 33,
      matchSample: 12,
      combos: [
        { label: '조합 A', pct: 30 },
        { label: '조합 B', pct: 17 },
      ],
      comboAce: [
        { name: 'Rho', acs: 235 },
        { name: 'Kai', acs: 214 },
      ],
      comboWeakness: [
        { name: 'Milo', fd: 31, acs: 198 },
        { name: 'Vex', fd: 27, acs: 180 },
      ],
    },
    '헤이븐': {
      mapWinRate: 42, atkWinRate: 38, defWinRate: 46,
      preferredSites: { A: 28, B: 30, center: 42 },
      avgSpikePlantTime: 36,
      matchSample: 10,
      combos: [
        { label: '조합 A', pct: 24 },
        { label: '조합 B', pct: 21 },
      ],
      comboAce: [
        { name: 'Kai', acs: 227 },
        { name: 'Zeta', acs: 251 },
      ],
      comboWeakness: [
        { name: 'Vex', fd: 30, acs: 175 },
        { name: 'Milo', fd: 26, acs: 190 },
      ],
    },
    '스플릿': {
      mapWinRate: 63, atkWinRate: 55, defWinRate: 58,
      preferredSites: { A: 50, B: 28, center: 22 },
      avgSpikePlantTime: 31,
      matchSample: 9,
      combos: [
        { label: '조합 A', pct: 33 },
        { label: '조합 B', pct: 18 },
      ],
      comboAce: [
        { name: 'Zeta', acs: 274 },
        { name: 'Rho', acs: 238 },
      ],
      comboWeakness: [
        { name: 'Vex', fd: 32, acs: 182 },
        { name: 'Milo', fd: 25, acs: 196 },
      ],
    },
    '로터스': {
      mapWinRate: 40, atkWinRate: 35, defWinRate: 44,
      preferredSites: { A: 26, B: 34, center: 40 },
      avgSpikePlantTime: 35,
      matchSample: 8,
      combos: [
        { label: '조합 A', pct: 21 },
        { label: '조합 B', pct: 20 },
      ],
      comboAce: [
        { name: 'Rho', acs: 229 },
        { name: 'Kai', acs: 211 },
      ],
      comboWeakness: [
        { name: 'Milo', fd: 28, acs: 187 },
        { name: 'Vex', fd: 24, acs: 170 },
      ],
    },
  },
  engagementInfo: {
    trade1v1: 61, trade1v2: 33,
    skills: [
      { name: '연막', engageRate: 35, successRate: 54 },
      { name: '플래시', engageRate: 31, successRate: 47 },
      { name: '감시 카메라', engageRate: 22, successRate: 66 },
    ],
    duelistVsDuelist: { us: 61, them: 39 },
    sentinelCompare: 'advantage',
  },
};

export const myTeamAiReportMock = {
  intro: 'Team Phoenix는 최근 20경기 기준 승률 65%로 안정적인 흐름을 유지하고 있습니다. 수비 라운드와 선취점 상황에서 강한 모습을 보이는 반면, Eco 라운드 승률과 1대2 열세 교전에서는 개선의 여지가 있습니다.',
  strengths: [
    '수비 승률 63%로 사이트 방어 조직력이 우수함',
    'FB Win % 71%로 선취점 이후 라운드 마무리 능력이 강함',
    '감시자 포지션 지표가 상대 대비 전반적으로 우위',
  ],
  weaknesses: [
    'Eco 라운드 승률 38%로 자금 열세 상황 대응이 부족함',
    '1대2 트레이드 성공률 33%로 다수 교전 대응력이 낮음',
    '바인드 승률 55%로 특정 맵 픽률 대비 성과가 아쉬움',
  ],
  tactic: 'Eco 라운드에서는 무리한 정면 교전 대신 정보 수집 위주의 운영으로 전환하고, 승리 시 다음 라운드 사이트 선점을 위한 얼리 로테이션을 권장합니다. 1대2 열세 상황에서는 스킬을 활용한 지연 후 팀 합류를 우선하는 방향이 유효할 것으로 예측됩니다.',
  playerFeedback: [
    { name: 'Zeta', role: '타격대', acs: 268, strength: '공격 라운드 K/D 1.5로 팀 내 가장 높은 진입 성공률을 보이며, 클러치 1v1 성공률 62%로 마무리 능력이 뛰어납니다.', weakness: '1대2 클러치 성공률이 28%로 다소 낮아, 다수 교전 상황에서는 무리한 진입보다 정보 공유 후 재정비를 권장합니다.' },
    { name: 'Rho', role: '척후대', acs: 241, strength: '정찰 스킬 활용도가 높아 팀의 초반 정보 획득에 크게 기여하고 있으며, 헤드샷 비율 24%로 안정적인 딜 교환이 가능합니다.', weakness: '수비 라운드에서의 포지셔닝이 다소 단조로워, 로테이션 타이밍을 다양화할 필요가 있습니다.' },
    { name: 'Kai', role: '감시자', acs: 220, strength: '수비 라운드 사이트 고정 능력이 뛰어나며, 스킬 유효율 지표가 팀 평균을 상회합니다.', weakness: '공격 시 존재감이 낮은 편으로, 유틸을 활용한 능동적인 사이트 진입 참여가 필요합니다.' },
    { name: 'Milo', role: '전략가', acs: 205, strength: '팀 합류 타이밍이 정확하고 궁극기 활용 시 교전 성사율이 67%로 매우 높습니다.', weakness: 'Eco 라운드에서의 생존율이 낮은 편으로, 무리한 정보 확인보다는 안전한 포지셔닝이 권장됩니다.' },
    { name: 'Vex', role: '타격대', acs: 188, strength: '서브 요원 폭이 넓어 밴픽 유연성에 기여하며, 최근 경기에서 성장세를 보이고 있습니다.', weakness: 'K/D 0.95로 팀 내 가장 낮은 지표를 기록 중이며, 진입 타이밍을 팀원과 더 긴밀히 맞출 필요가 있습니다.' },
  ],
};
