import AiReportCard from '../../components/aiReport/AiReportCard';
import PlayerFeedbackCard from '../../components/aiReport/PlayerFeedbackCard';

export default function AiReportTab({ report, teamName }) {
  return (
    <>
      <div className="section-title mb">팀 전술 리포트</div>
      <AiReportCard
        report={report}
        heading={`AI 전술 리포트 — ${teamName}`}
        strengthTitle="팀 강점 3"
        weaknessTitle="팀 약점 3"
      />

      <div className="section-title spaced">선수 개인별 피드백</div>
      {report.playerFeedback.map((f) => (
        <PlayerFeedbackCard feedback={f} key={f.name} />
      ))}
    </>
  );
}