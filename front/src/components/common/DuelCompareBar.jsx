import React from 'react';

/**
 * 우리팀 vs 상대팀 100% 스택 바(part-to-whole, 항상 두 값의 합이 100).
 * size="lg"는 그 화면에서 가장 중요한 결과 하나를 강조할 때만 쓴다(예:
 * EngagementPredictionBlock의 "최종 교전 승률") - 기본값(size 생략)은 보조 지표용
 * 컴팩트 스타일이다.
 */
export default function DuelCompareBar({
  leftLabel = '우리팀',
  leftPct = 50,
  rightLabel = '상대팀',
  rightPct = 50,
  size = 'md',
}) {
  const total = leftPct + rightPct;
  const leftWidth = total > 0 ? (leftPct / total) * 100 : 50;
  const rightWidth = total > 0 ? (rightPct / total) * 100 : 50;

  const displayLeft = Number(leftPct).toFixed(1);
  const displayRight = Number(rightPct).toFixed(1);
  // PredictBox(위쪽 "예상 승률")의 pv-percent.is-high/is-low와 같은 규칙 - 우세한 쪽
  // 퍼센트 글자를 더 크고 진하게, 열세한 쪽은 더 작고 흐리게 표시한다.
  const isLeftHigh = leftPct >= rightPct;

  return (
    <div className={`duel-compare duel-compare--${size}`}>
      <div className="duel-compare-labels">
        <div className="duel-compare-label us">
          <span className="team-name">{leftLabel}</span>
          <b className={`team-pct ${isLeftHigh ? 'is-high' : 'is-low'}`}>{displayLeft}%</b>
        </div>
        <div className="duel-compare-label them">
          <b className={`team-pct ${!isLeftHigh ? 'is-high' : 'is-low'}`}>{displayRight}%</b>
          <span className="team-name">{rightLabel}</span>
        </div>
      </div>

      {/* 두 구간 사이 2px 서피스 간격이 실제 분리 장치 - 테두리 대신 배경색이 비쳐 보이게 함 */}
      <div className="duel-compare-bar">
        <div className="seg us" style={{ width: `calc(${leftWidth}% - 1px)` }} />
        <div className="seg them" style={{ width: `calc(${rightWidth}% - 1px)` }} />
      </div>
    </div>
  );
}
