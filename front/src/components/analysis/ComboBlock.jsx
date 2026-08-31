export default function ComboBlock({ title = '선호 요원 조합', combos, ace, weakness }) {
  return (
    <div className="combo-block">
      <div className="combo-block-title">{title}</div>
      {combos.map((c) => (
        <div className="combo-row" key={c.label}>
          <span className="combo-label">{c.label}</span>
          <div className="combo-agents">
            {Array.from({ length: 5 }).map((_, i) => (
              <div className="combo-agent-icon" key={i} />
            ))}
          </div>
          <span className="combo-pct">{c.pct}%</span>
        </div>
      ))}

      <div className="combo-detail-cols">
        <div>
          <div className="combo-detail-title text-win">BEST</div>
          {ace.map((p) => (
            <div className="combo-detail-row" key={p.name}>
              <span>{p.name}</span>
              <b>ACS {p.acs}</b>
            </div>
          ))}
        </div>
        <div>
          <div className="combo-detail-title text-lose">WORST</div>
          {weakness.map((p) => (
            <div className="combo-detail-row" key={p.name}>
              <span>{p.name}</span>
              <b>FD {p.fd}% · ACS {p.acs}</b>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}