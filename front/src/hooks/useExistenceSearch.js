import { useState } from 'react';
import { checkPlayerExists, checkTeamExists } from '../api/search';

// 이름#태그 형식 검사 (개인/팀 공통)
const isValidFormat = (input) => /^.+#.+$/.test(input.trim());

// 개인/팀 검색창 3곳(SearchBox, HeaderSearchBar, ModalTeamSearchBar)이 각자 똑같이
// 구현하던 "형식 검사 → 존재확인 API 호출 → 에러 토스트/로딩" 로직을 하나로 합친 훅.
// 존재확인 이후 할 일(페이지 이동/콜백)은 컴포넌트마다 달라서 그건 호출부가 처리한다.
export function useExistenceSearch() {
  const [errorMessage, setErrorMessage] = useState('');
  const [showErrorToast, setShowErrorToast] = useState(false);
  const [loading, setLoading] = useState(false);

  const triggerErrorToast = (msg) => {
    setErrorMessage(msg);
    setShowErrorToast(true);
    setTimeout(() => setShowErrorToast(false), 3000);
  };

  // type: 'player' | 'team'. 존재하면 { namePart, tagPart } 반환, 아니면 null(토스트는 이미 띄움).
  const checkExists = async (rawInput, type) => {
    const trimmed = rawInput.trim();
    if (!trimmed) {
      triggerErrorToast('검색어를 입력해 주세요.');
      return null;
    }
    if (!isValidFormat(trimmed)) {
      triggerErrorToast(
        `올바른 형식으로 입력해 주세요. ( ex. ${type === 'player' ? '뇽따까리#0208' : '팀명#태그'} )`
      );
      return null;
    }

    const [namePart, tagPart] = trimmed.split('#');
    setLoading(true);
    try {
      const res = type === 'player'
        ? await checkPlayerExists(namePart, tagPart)
        : await checkTeamExists(namePart, tagPart);
      if (!res.exists) {
        triggerErrorToast(type === 'player' ? '존재하지 않는 닉네임입니다.' : '존재하지 않는 팀입니다.');
        return null;
      }
      return { namePart, tagPart };
    } catch {
      triggerErrorToast('검색 중 오류가 발생했습니다.');
      return null;
    } finally {
      setLoading(false);
    }
  };

  return { checkExists, loading, errorMessage, showErrorToast };
}
