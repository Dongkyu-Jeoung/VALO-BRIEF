export default function SelectBox({ label, options, value, onChange, className = '' }) {
  if (!options || !onChange) {
    return <div className={`select-box ${className}`.trim()}>{label} ▾</div>;
  }

  return (
    <div className={`select-box ${className}`.trim()}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
      <span aria-hidden="true">▾</span>
    </div>
  );
}
