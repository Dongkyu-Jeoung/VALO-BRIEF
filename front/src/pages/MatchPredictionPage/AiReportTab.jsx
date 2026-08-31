import PhaseRow from '../../components/aiReport/PhaseRow';
import OpponentPickAnalysis from '../../components/aiReport/OpponentPickAnalysis';

export default function AiReportTab({ report, opponentName }) {
  return (
    <div className="ai-report-card">
      <div className="popup-head plain">
        <div className="bolt" />
        <div className="popup-title display lg">AI 전술 리포트 — {opponentName} 분석</div>
      </div>
      <div className="ai-intro">{report.intro}</div>
      <div className="ai-cols">
        <div>
          <div className="ai-strength-title win">상대 팀 강점 3</div>
          {report.strengths.map((s, i) => (
            <div className="ai-list-item" key={i}><span className="num">{String(i + 1).padStart(2, '0')}</span>{s}</div>
          ))}
        </div>
        <div>
          <div className="ai-strength-title lose">상대 팀 약점 3</div>
          {report.weaknesses.map((w, i) => (
            <div className="ai-list-item" key={i}><span className="num">{String(i + 1).padStart(2, '0')}</span>{w}</div>
          ))}
        </div>
      </div>
      <div className="ai-tactic-box"><b>전술 제안 —</b> {report.tactic}</div>
      <div className="ai-report-section">
        <PhaseRow phases={report.phases} />
      </div>
      <div className="ai-report-section">
        <OpponentPickAnalysis text={report.opponentPickAnalysisText} />
      </div>
    </div>
  );
}