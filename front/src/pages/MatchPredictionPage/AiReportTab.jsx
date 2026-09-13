import AiReportCard from '../../components/aiReport/AiReportCard';
import PhaseRow from '../../components/aiReport/PhaseRow';
import OpponentPickAnalysis from '../../components/aiReport/OpponentPickAnalysis';

export default function AiReportTab({ report, status, opponentName }) {
  // status === 'generating': 기준정보(team_engagement_cache)는 있어서 백엔드가 방금
  // Claude 생성을 백그라운드로 시작시켰다(services/opponent_ai_report.py 참고, 20~45초
  // 걸림) - MatchPredictionPage/index.jsx가 몇 초 간격으로 다시 조회 중이니 여기선 그냥
  // 안내만 보여준다.
  if (status === 'generating') {
    return (
      <div className="ai-report-card">
        <div className="popup-head plain">
          <div className="bolt" />
          <div className="popup-title display lg">AI 전술 리포트 — {opponentName} 팀 분석</div>
        </div>
        <div className="empty-text">
          AI가 {opponentName} 팀의 전술 리포트를 생성하고 있습니다. 최대 1분 정도 걸릴 수
          있어요 - 이 화면은 자동으로 갱신됩니다.
        </div>
      </div>
    );
  }

  // report는 정상적으로 null일 수 있다 - 상대팀 기준정보가 아직 DB에 없는 경우
  // (services/opponent_ai_report.py::_has_cached_data가 false를 준 경우, 한 번도
  // 검색/조회된 적 없는 팀). 이 팀을 "통계"/"분석" 탭에서 한 번이라도 열어보면 백그라운드
  // write-through로 기준정보가 쌓이고, 다음 조회부터 리포트가 생성된다.
  if (!report) {
    return (
      <div className="ai-report-card">
        <div className="popup-head plain">
          <div className="bolt" />
          <div className="popup-title display lg">AI 전술 리포트 — {opponentName} 팀 분석</div>
        </div>
        <div className="empty-text">
          아직 {opponentName} 팀의 데이터가 충분히 쌓이지 않아 AI 리포트를 준비 중입니다.
          &ldquo;통계&rdquo;/&ldquo;분석&rdquo; 탭을 한 번 열어보시면 곧 생성됩니다.
        </div>
      </div>
    );
  }

  return (
    <AiReportCard
      report={report}
      heading={`AI 전술 리포트 — ${opponentName} 팀 분석`}
      strengthTitle="상대 팀 강점 3"
      weaknessTitle="상대 팀 약점 3"
    >
      <div className="ai-report-section">
        <PhaseRow phases={report.phases} />
      </div>
      <div className="ai-report-section">
        <OpponentPickAnalysis data={report.opponentPickAnalysis} />
      </div>
    </AiReportCard>
  );
}