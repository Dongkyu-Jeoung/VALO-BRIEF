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
              <div className="ai-list-head">
                <span className="num win">{String(i + 1).padStart(2, '0')}</span>
                <b className="ai-item-title">{s.title}</b>
              </div>
              {s.stat && <span className="stat-badge win">{s.stat}</span>}
              {s.detail.map((line, j) => (
                <p className="ai-list-detail" key={j}>{line}</p>
              ))}
            </div>
          ))}
        </div>
        <div>
          <div className="ai-strength-title lose">{weaknessTitle}</div>
          {report.weaknesses.map((w, i) => (
            <div className="ai-list-item" key={i}>
              <div className="ai-list-head">
                <span className="num lose">{String(i + 1).padStart(2, '0')}</span>
                <b className="ai-item-title">{w.title}</b>
              </div>
              {w.stat && <span className="stat-badge lose">{w.stat}</span>}
              {w.detail.map((line, j) => (
                <p className="ai-list-detail" key={j}>{line}</p>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="ai-tactic-box">
        <div className="ai-tactic-heading">전술 제안</div>
        <div className="ai-tactic-list">
          {report.tactic.map((t, i) => (
            <div className="ai-tactic-item" key={i}>
              <div className="ai-tactic-item-head">
                <span className="tactic-num">{i + 1}</span>
              </div>
              <div className="ai-list-body">
                <b className="ai-list-title">{t.title}</b>
                {t.detail.map((line, j) => (
                  <p className="ai-list-detail" key={j}>{line}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}