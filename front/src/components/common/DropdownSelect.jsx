import { useEffect, useRef, useState } from 'react';

export default function DropdownSelect({ icon, label, options, value, onChange, variant = 'map', onClick }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const cls = variant === 'user' ? 'user-select' : 'map-select';

  useEffect(() => {
    if (!open) return undefined;
    function handleOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [open]);

  if (!options) {
    return (
      <button className={cls} type="button" onClick={onClick}>
        {icon ? <span>{icon}</span> : null} {label} ▾
      </button>
    );
  }

  return (
    <div className={`${cls}-wrap`} ref={wrapRef}>
      <button className={cls} type="button" onClick={() => setOpen((o) => !o)}>
        {icon ? <span>{icon}</span> : null} {label} ▾
      </button>
      {open ? (
        <ul className="dropdown-popover">
          {options.map((opt) => (
            <li key={opt}>
              <button
                type="button"
                className={opt === value ? 'is-active' : ''}
                onClick={() => {
                  onChange?.(opt);
                  setOpen(false);
                }}
              >
                {opt}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}