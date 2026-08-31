export default function DuelCompareBar({ leftLabel, leftPct, rightLabel, rightPct }) {
  return (
    <div className="duel-compare">
      <div className="duel-side-label">
        {leftLabel}
        <b>{leftPct}%</b>
      </div>
      <div className="duel-bar">
        <div className="us" style={{ width: `${leftPct}%` }} />
        <div className="them" style={{ width: `${rightPct}%` }} />
      </div>
      <div className="duel-side-label right">
        {rightLabel}
        <b>{rightPct}%</b>
      </div>
    </div>
  );
}