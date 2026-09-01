import React from 'react';

export default function DuelCompareBar({ 
  leftLabel = '우리팀', 
  leftPct = 50, 
  rightLabel = '상대팀', 
  rightPct = 50 
}) {
  return (
    <div className="duel-compare">
      {/* 좌측: 우리팀 */}
      <div className="duel-side-label us">
        <span className="team-name">{leftLabel}</span>
        <b className="team-pct">{leftPct}%</b>
      </div>

      {/* 중앙 게이지 바 */}
      <div className="duel-bar">
        <div className="us" style={{ width: `${leftPct}%` }} />
        <div className="them" style={{ width: `${rightPct}%` }} />
      </div>

      {/* 우측: 상대팀 */}
      <div className="duel-side-label them">
        <span className="team-name">{rightLabel}</span>
        <b className="team-pct">{rightPct}%</b>
      </div>
    </div>
  );
}