// 백엔드(services/opponent_ai_report.py::_highlight_player_names)가 실제 로스터
// 닉네임을 **닉네임**으로 감싸서 내려준다 - "kyokkyokk·Lily 선수 중심..."처럼 다른
// 텍스트와 구분 없이 섞이던 닉네임을 배지로 명확히 분리해서 보여준다.
function renderWithPlayerNames(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <span className="ai-player-name" key={i}>{part.slice(2, -2)}</span>;
    }
    return part;
  });
}

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
          <p className="ai-list-detail" key={i}>{renderWithPlayerNames(line)}</p>
        ))}
      </div>
    </>
  );
}