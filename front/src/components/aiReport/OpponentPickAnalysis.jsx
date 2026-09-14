export default function OpponentPickAnalysis({ data }) {
  return (
    <>
      <div className="ai-strength-title">상대 요원 선택 분석</div>
      <div className="ai-pick-analysis-box">
        <b className="ai-list-title">{data.title}</b>
        {data.stat && <span className="stat-badge accent">{data.stat}</span>}
        {data.detail.map((line, i) => (
          <p className="ai-list-detail" key={i}>{line}</p>
        ))}
      </div>
    </>
  );
}
