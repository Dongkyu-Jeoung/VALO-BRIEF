export default function SelectBox({ label, options, value, onChange, className = '' }) {
  if (!options || !onChange) {
    return <div className={`select-box ${className}`.trim()}>{label} ▾</div>;
  }

  return (
    <div className={`select-box ${className}`.trim()}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => {
          const optValue = typeof opt === 'object' && opt !== null ? opt.id : opt;
          const optLabel = typeof opt === 'object' && opt !== null ? opt.name : opt;

          return (
            <option key={optValue} value={optValue}>
              {optLabel}
            </option>
          );
        })}
      </select>
    </div>
  );
}