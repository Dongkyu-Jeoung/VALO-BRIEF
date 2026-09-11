import PhaseRow from '../../components/aiReport/PhaseRow';
import OpponentPickAnalysis from '../../components/aiReport/OpponentPickAnalysis';

export default function AiReportTab({ report, opponentName }) {
  // report는 정상적으로 null일 수 있다 - 상대팀 기준정보가 아직 DB에 없는 경우
  // (services/opponent_ai_report.py::_has_cached_data가 false를 준 경우, 한 번도
  // 검색/조회된 적 없는 팀). 이 팀을 "통계"/"분석" 탭에서 한 번이라도 열어보면 백그라운드
  // write-through로 기준정보가 쌓이고, 다음 조회부터 리포트가 생성된다.
  if (!report) {
    return (
      <div className="ai-report-card">
        <div className="popup-head plain">
          <div className="bolt" />
          <div className="popup-title display lg">AI 전술 리포트 — {opponentName} 분석</div>
        </div>
        <div className="empty-text">
          아직 {opponentName}의 데이터가 충분히 쌓이지 않아 AI 리포트를 준비 중입니다.
          &ldquo;통계&rdquo;/&ldquo;분석&rdquo; 탭을 한 번 열어보시면 곧 생성됩니다.
        </div>
      </div>
    );
  }

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