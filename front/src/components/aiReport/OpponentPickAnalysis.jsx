export default function OpponentPickAnalysis({ data }) {
  return (
    <>
      <div className="ai-section-heading">상대 요원 선택 분석</div>
      <div className="ai-pick-analysis-box">
        <div className="ai-pick-analysis-head">
          <b className="ai-list-title">{data.title}</b>
          {data.stat && <span className="stat-badge accent">{data.stat}</span>}
        </div>
        {data.detail.map((line, i) => (
          <p className="ai-list-detail" key={i}>{line}</p>
        ))}
      </div>
    </>
  );
}