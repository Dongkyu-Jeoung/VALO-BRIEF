export default function DonutChart({ winPct, size = 96, className = '' }) {
  const deg = (winPct / 100) * 360;
  return (
    <div
      className={`donut-chart ${className}`.trim()}
      style={{ '--donut-size': `${size}px`, '--donut-deg': `${deg}deg` }}
    >
      <span className="donut-chart-inner">{winPct}%</span>
    </div>
  );
}