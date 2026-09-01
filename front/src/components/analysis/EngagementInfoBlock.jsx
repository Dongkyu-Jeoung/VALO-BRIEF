import StatInlineGrid from '../common/StatInlineGrid';
import DuelCompareBar from '../common/DuelCompareBar';

export default function EngagementInfoBlock({ 
  data, 
  title = '③ 교전 정보', 
  tradeTitle = '트레이드 성공률', 
  ourLabel = '우리팀', 
  theirLabel = '상대팀' 
}) {
  const duel = data.duelistVsDuelist ?? data.duelistCompare ?? { us: 50, them: 50 };
  const leftPct = duel.us ?? duel.me;
  const rightPct = duel.them ?? duel.opponent;

  return (
    <div className="analysis-row">
      <div className="analysis-row-head">
        <h5>{title}</h5>
      </div>

      {/* 트레이드 성공률 */}
      <div className="duel-compare-block">
        <div className="duel-compare-title">{tradeTitle}</div>
        <StatInlineGrid
          columns={2}
          items={[
            { label: '1대1 상황', value: `${data.trade1v1}%` },
            { label: '1대2 상황', value: `${data.trade1v2}%` },
          ]}
        />
      </div>

      {/* 스킬 사용 유효성 */}
      <div className="duel-compare-block">
        <div className="duel-compare-title">스킬 사용 유효성 (스킬명 · 교전 성사율 · 성공률)</div>
        <div className="skill-box-row">
          {data.skills.map((s) => (
            <div className="skill-box" key={s.name}>
              <div className="sk-name">{s.name}</div>
              <div className="sk-metrics">
                <div>교전 성사율<b>{s.engageRate}%</b></div>
                <div>성공률<b>{s.successRate}%</b></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 타격대 vs 타격대 비교 */}
      <div className="duel-compare-block">
        <div className="duel-compare-title">타격대 vs 타격대 비교</div>
        <DuelCompareBar 
          leftLabel={ourLabel} 
          leftPct={leftPct} 
          rightLabel={theirLabel} 
          rightPct={rightPct} 
        />
      </div>
    </div>
  );
}