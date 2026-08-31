export default function PhaseRow({ phases }) {
  return (
    <>
      <div className="ai-strength-title">라운드 페이즈별 예상 전개</div>
      <div className="ai-phase-row">
        {phases.map((p) => (
          <div className="ai-phase-box" key={p.label}>
            <div className="phase-label">{p.label}</div>
            <p>{p.text}</p>
          </div>
        ))}
      </div>
    </>
  );
}