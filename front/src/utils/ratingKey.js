// division/rank 표기 문자열 -> assets/images/rating 폴더의 파일명(key)으로 변환
// 필요에 따라 매핑을 자유롭게 추가하세요.
const MAP = {
  '디비전 1': 'division-1',
  '디비전 2': 'division-2',
  '디비전 3': 'division-3',
  '디비전 4': 'division-4',
  '디비전 5': 'division-5',
};

export function ratingKey(label = '') {
  if (MAP[label]) return MAP[label];
  if (label.includes('레디언트')) return 'radiant';
  if (label.includes('불멸')) return 'immortal';
  if (label.includes('초월자')) return 'ascendant';
  if (label.includes('다이아')) return 'diamond';
  if (label.includes('플래티넘')) return 'platinum';
  if (label.includes('골드')) return 'gold';
  if (label.includes('실버')) return 'silver';
  if (label.includes('브론즈')) return 'bronze';
  if (label.includes('아이언')) return 'iron';
  return null;
}
