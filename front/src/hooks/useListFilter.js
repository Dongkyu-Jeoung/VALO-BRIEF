import { useMemo } from 'react';

// items 배열을 predicate로 클라이언트 사이드 필터링하는 공용 훅.
// predicate가 매 렌더마다 새로 생성돼도 안전하도록 items/predicate 둘 다 의존성에 둡니다.
export function useListFilter(items, predicate) {
  return useMemo(() => (items ?? []).filter(predicate), [items, predicate]);
}
