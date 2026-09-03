import EmptyImageBox from '../common/EmptyImageBox';

export default function ComboBlock({ title = '선호 요원 조합', combos = [], ace = [], weakness = [] }) {
  return (
    <div className="combo-block">
      <div className="combo-block-title">{title}</div>
      {combos?.map((c) => (
        <div className="combo-row" key={c.label}>
          <span className="combo-label">{c.label}</span>
          <div className="combo-agents">
            {c.agents ? c.agents.map((agentKey, i) => (
              <EmptyImageBox className="combo-agent-icon" folder="agents" assetKey={agentKey} key={i} />
            )) : Array.from({ length: 5 }).map((_, i) => (
              <div className="combo-agent-icon" key={i} />
            ))}
          </div>
          <span className="combo-pct">{c.pct}%</span>
        </div>
      ))}

      <div className="combo-detail-cols">
        <div>
          <div className="combo-detail-title text-win">BEST</div>
          {ace?.map((p) => (
            <div className="combo-detail-row" key={p.name}>
              <span>{p.name}</span>
              <div className="stats-group">
                <b>ACS {p.acs}</b>
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="combo-detail-title text-lose">WORST</div>
          {weakness?.map((p) => (
            <div className="combo-detail-row" key={p.name}>
              <span>{p.name}</span>
              <div className="stats-group">
                <b>FD {p.fd}%</b>
                <span>·</span>
                <b>ACS {p.acs}</b>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}