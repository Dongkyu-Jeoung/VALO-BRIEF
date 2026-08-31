import EmptyImageBox from '../common/EmptyImageBox';

export default function PlayerFeedbackCard({ feedback }) {
  return (
    <div className="ai-feedback-card">
      <EmptyImageBox className="ai-feedback-avatar" label="" />
      <div className="ai-feedback-body">
        <div className="ai-feedback-name">
          {feedback.name} <span className="tag">{feedback.role} · ACS {feedback.acs}</span>
        </div>
        <div className="ai-feedback-cols">
          <div>
            <div className="lbl text-win">강점</div>
            <p>{feedback.strength}</p>
          </div>
          <div>
            <div className="lbl text-lose">보완점</div>
            <p>{feedback.weakness}</p>
          </div>
        </div>
      </div>
    </div>
  );
}