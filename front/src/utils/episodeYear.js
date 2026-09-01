// Riot 공식 Episode 표기("Episode 11")를 화면 표시용 "연도" 라벨("2026")로 변환합니다.
// 연도 = Episode 번호 + 2015 (Episode 11 = 2026년, Episode 12 = 2027년 ...).
// 오프셋 하나만 유지하면 되므로, 새 Episode가 나와도 코드 수정 없이 다음 연도로 자동 표시됩니다.
// 백엔드/쿼리 파라미터는 계속 "Episode N"을 쓰고(Henrik mmr-history의 by_season 키와
// 맞아야 하므로), 이 변환은 프론트 표시 경계(api/players.js)에서만 적용합니다.
const EPISODE_YEAR_OFFSET = 2015;

export function episodeToYearLabel(episodeLabel) {
  const m = /^Episode\s+(\d+)$/i.exec(episodeLabel ?? '');
  if (!m) return episodeLabel;
  return String(Number(m[1]) + EPISODE_YEAR_OFFSET);
}

export function yearLabelToEpisode(yearLabel) {
  const n = Number(yearLabel);
  if (!Number.isFinite(n)) return yearLabel;
  return `Episode ${n - EPISODE_YEAR_OFFSET}`;
}
