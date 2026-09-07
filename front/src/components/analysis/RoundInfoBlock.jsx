import StatInlineGrid from '../common/StatInlineGrid';

/**
 * data: { atkWinRate, defWinRate, pistolWinRate, ecoWinRate, fbWinPct, fdLosePct }
 * 승부예측(Frame07) / 우리팀 분석-팀분석탭(Frame12) 공용
 */
export default function RoundInfoBlock({ data }) {
  const d = data || {};
  
  const items = [
    { label: '공격 승률', value: `${d.atkWinRate ?? d.attackWinRate ?? 0}%` },
    { label: '수비 승률', value: `${d.defWinRate ?? d.defenseWinRate ?? 0}%` },
    { label: '피스톨 라운드 승률', value: `${d.pistolWinRate ?? 50}%` },
    { label: 'Eco 라운드 승률', value: `${d.ecoWinRate ?? 0}%` },
    { label: 'FB Win %', value: `${d.fbWinPct ?? d.fbWinRate ?? d.fbWin ?? 0}%`, sub: '선취점 획득 시' },
    { label: 'FD Lose %', value: `${d.fdLosePct ?? d.fdLoseRate ?? d.fdLose ?? 0}%`, sub: '한 명 손실 시' },
  ];

  return (
    <div className="analysis-row">
      <div className="analysis-row-head"><h5>① 라운드 정보</h5></div>
      <StatInlineGrid items={items} columns={6} />
    </div>
  );
}