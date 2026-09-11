import EmptyImageBox from '../common/EmptyImageBox';

export default function PlayerFeedbackCard({ feedback }) {
  return (
    <div className="ai-feedback-card">
      <EmptyImageBox className="ai-feedback-avatar" src={feedback.avatarUrl} label="" />
      <div className="ai-feedback-body">
        <div className="ai-feedback-name">
          {feedback.name} <span className="tag">{feedback.role} · ACS {feedback.acs}</span>
        </div>
        <div className="ai-feedback-cols">
          <div>
            <div className="lbl text-win">강점</div>
            {feedback.strength.stat && <span className="stat-badge win">{feedback.strength.stat}</span>}
            <b className="ai-list-title">{feedback.strength.title}</b>
            {feedback.strength.detail.map((line, i) => (
              <p className="ai-list-detail" key={i}>{line}</p>
            ))}
          </div>
          <div>
            <div className="lbl text-lose">보완점</div>
            {feedback.weakness.stat && <span className="stat-badge lose">{feedback.weakness.stat}</span>}
            <b className="ai-list-title">{feedback.weakness.title}</b>
            {feedback.weakness.detail.map((line, i) => (
              <p className="ai-list-detail" key={i}>{line}</p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}