import React from 'react';
import StatInlineGrid from '../common/StatInlineGrid';
import DuelCompareBar from '../common/DuelCompareBar';
import DeathMapTracker from './DeathMapTracker';

export default function EngagementInfoBlock({ 
  data, 
  title = '③ 교전 정보', 
  tradeTitle = '트레이드 성공률', 
  ourLabel = '우리팀', 
  theirLabel = '상대팀',
  selectedMapId 
}) {
  if (!data) return null;

  const duel = data.duelistVsDuelist ?? data.duelistCompare ?? { us: 50, them: 50 };
  const leftPct = duel.us ?? duel.me ?? 50;
  const rightPct = duel.them ?? duel.opponent ?? 50;

  return (
    <div className="analysis-row">
      <div className="analysis-row-head">
        <h5>{title}</h5>
      </div>

      <div className="duel-compare-block">
        <div className="duel-compare-title">{tradeTitle}</div>
        <StatInlineGrid
          columns={2}
          items={[
            { label: '1대1 상황', value: `${data.trade1v1 ?? '-'}%` },
            { label: '1대2 상황', value: `${data.trade1v2 ?? '-'}%` },
          ]}
        />
      </div>

      <div className="duel-compare-block">
        <div className="duel-compare-title">팀원 사망 위치 분석</div>
        <DeathMapTracker 
          selectedMapId={selectedMapId} 
          deathData={data.deaths ?? []} 
        />
      </div>

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