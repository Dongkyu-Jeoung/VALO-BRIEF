import StatInlineGrid from '../common/StatInlineGrid';

/**
 * data: { atkWinRate, defWinRate, pistolWinRate, ecoWinRate, fbWinPct, fdLosePct }
 * 승부예측(Frame07) / 우리팀 분석-팀분석탭(Frame12) 공용
 */
export default function RoundInfoBlock({ data }) {
  const items = [
    { label: '공격 승률', value: `${data.atkWinRate}%` },
    { label: '수비 승률', value: `${data.defWinRate}%` },
    { label: '피스톨 라운드 승률', value: `${data.pistolWinRate}%` },
    { label: 'Eco 라운드 승률', value: `${data.ecoWinRate}%` },
    { label: 'FB Win %', value: `${data.fbWinPct}%`, sub: '선취점 획득 시' },
    { label: 'FD Lose %', value: `${data.fdLosePct}%`, sub: '한 명 손실 시' },
  ];
  return (
    <div className="analysis-row">
      <div className="analysis-row-head"><h5>① 라운드 정보</h5></div>
      <StatInlineGrid items={items} columns={6} />
    </div>
  );
}
