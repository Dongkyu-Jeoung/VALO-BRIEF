export function pct(value) {
  return value === null || value === undefined ? '—' : `${value}%`;
}

export function num(value, fallback = '—') {
  return value === null || value === undefined ? fallback : value;
}
