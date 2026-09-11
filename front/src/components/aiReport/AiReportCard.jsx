export default function AiReportCard({ report, heading, strengthTitle = '강점 3', weaknessTitle = '약점 3' }) {
  return (
    <div className="ai-report-card">
      <div className="popup-head plain">
        <div className="bolt" />
        <div className="popup-title display lg">{heading}</div>
      </div>
      <div className="ai-intro">{report.intro}</div>
      <div className="ai-cols">
        <div>
          <div className="ai-strength-title win">{strengthTitle}</div>
          {report.strengths.map((s, i) => (
            <div className="ai-list-item" key={i}>
              <span className="num win">{String(i + 1).padStart(2, '0')}</span>
              <div className="ai-list-body">
                {s.stat && <span className="stat-badge win">{s.stat}</span>}
                <b className="ai-list-title">{s.title}</b>
                {s.detail.map((line, j) => (
                  <p className="ai-list-detail" key={j}>{line}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="ai-strength-title lose">{weaknessTitle}</div>
          {report.weaknesses.map((w, i) => (
            <div className="ai-list-item" key={i}>
              <span className="num lose">{String(i + 1).padStart(2, '0')}</span>
              <div className="ai-list-body">
                {w.stat && <span className="stat-badge lose">{w.stat}</span>}
                <b className="ai-list-title">{w.title}</b>
                {w.detail.map((line, j) => (
                  <p className="ai-list-detail" key={j}>{line}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="ai-tactic-box">
        <b>전술 제안 —</b> {report.tactic}
      </div>
    </div>
  );
}