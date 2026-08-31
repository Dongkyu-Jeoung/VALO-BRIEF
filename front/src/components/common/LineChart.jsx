/**
 * 의존성 없이 순수 SVG로 그리는 단일 라인 차트.
 * points: [{ x: string, y: number }]  x는 카테고리 라벨(거리 구간 등), y는 수치.
 */
export default function LineChart({ points, width = 560, height = 160, className = '' }) {
  if (!points || points.length === 0) return null;

  const padding = { top: 16, right: 16, bottom: 28, left: 16 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const maxY = Math.max(...points.map((p) => p.y), 1);
  const stepX = points.length > 1 ? innerWidth / (points.length - 1) : 0;

  const coords = points.map((p, i) => ({
    x: padding.left + i * stepX,
    y: padding.top + innerHeight - (p.y / maxY) * innerHeight,
  }));

  const polylinePoints = coords.map((c) => `${c.x},${c.y}`).join(' ');

  return (
    <svg className={`line-chart ${className}`.trim()} viewBox={`0 0 ${width} ${height}`} width="100%" height={height}>
      {[0, 0.5, 1].map((r) => (
        <line
          key={r}
          x1={padding.left}
          x2={width - padding.right}
          y1={padding.top + innerHeight * r}
          y2={padding.top + innerHeight * r}
          className="line-chart-grid"
        />
      ))}
      <polyline points={polylinePoints} className="line-chart-line" fill="none" />
      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r={3.5} className="line-chart-dot" />
      ))}
      {points.map((p, i) => (
        <text key={p.x} x={coords[i].x} y={height - 8} textAnchor="middle" className="line-chart-label">
          {p.x}
        </text>
      ))}
    </svg>
  );
}
