import { useState } from 'react';
import MatchRow from './MatchRow';

export default function MatchHistoryList({ matches, total = 20 }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? matches : matches.slice(0, 5);
  return (
    <div>
      <div className="match-list-head">
        <h5 className="section-title">매치 히스토리</h5>
        <span className="tag">{total} MATCHES</span>
      </div>
      {visible.map((m, i) => (
        <MatchRow match={m} key={i} />
      ))}
      {!showAll && matches.length > visible.length ? (
        <div className="show-more" onClick={() => setShowAll(true)} role="button" tabIndex={0}>
          + Show More
        </div>
      ) : null}
    </div>
  );
}