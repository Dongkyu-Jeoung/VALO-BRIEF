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
    } catch (err) {
      // 백엔드가 Henrik 레이트리밋(429)에 걸리면 503 + 안내 메시지로 응답한다
      // (server/main.py의 HenrikRateLimitError 핸들러 참고) - 이걸 "존재하지 않음"과 같은
      // 일반 에러 문구로 보여주면 실제로는 존재하는데 검색이 그냥 안 되는 것처럼 오해하기
      // 쉬워서 별도 메시지로 구분한다.
      const isRateLimited = err instanceof Error && err.message.startsWith('[HTTP 503]');
      triggerErrorToast(
        isRateLimited
          ? '요청이 많아 잠시 조회할 수 없습니다. 몇 초 후 다시 시도해 주세요.'
          : '검색 중 오류가 발생했습니다.'
      );
      return null;
    } finally {
      setLoading(false);
    }
  };

  return { checkExists, loading, errorMessage, showErrorToast };
}
