import React from 'react';

export default function DuelCompareBar({ 
  leftLabel = '우리팀', 
  leftPct = 50, 
  rightLabel = '상대팀', 
  rightPct = 50 
}) {
  const total = leftPct + rightPct;
  const leftWidth = total > 0 ? (leftPct / total) * 100 : 50;
  const rightWidth = total > 0 ? (rightPct / total) * 100 : 50;

  const displayLeft = Number(leftPct).toFixed(1);
  const displayRight = Number(rightPct).toFixed(1);

  return (
    <div className="duel-compare">
      {/* 좌측: 우리팀 */}
      <div className="duel-side-label us">
        <span className="team-name">{leftLabel}</span>
        <b className="team-pct">{displayLeft}%</b>
      </div>

      {/* 중앙 게이지 바 */}
      <div className="duel-bar">
        <div className="us" style={{ width: `${leftWidth}%` }} />
        <div className="them" style={{ width: `${rightWidth}%` }} />
      </div>

      {/* 우측: 상대팀 */}
      <div className="duel-side-label them">
        <span className="team-name">{rightLabel}</span>
        <b className="team-pct">{displayRight}%</b>
      </div>
    </div>
  );
}