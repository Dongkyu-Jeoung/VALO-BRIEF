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
              <span className="num">{String(i + 1).padStart(2, '0')}</span>{s}
            </div>
          ))}
        </div>
        <div>
          <div className="ai-strength-title lose">{weaknessTitle}</div>
          {report.weaknesses.map((w, i) => (
            <div className="ai-list-item" key={i}>
              <span className="num">{String(i + 1).padStart(2, '0')}</span>{w}
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