import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { checkPlayerExists, checkTeamExists } from '../../api/search';
import { ROUTES } from '../../constants/routes';
import '../../styles/components/header-search-bar.css';

const isValidFormat = (input) => /^.+#.+$/.test(input.trim());

/**
 * 헤더(햄버거 메뉴 왼쪽)에 들어가는 검색창. 토글 없이 현재 페이지 종류에 맞춰
 * 개인/팀 검색을 자동으로 전환합니다.
 * - /players 이하: 개인 검색 → 선수 프로필로 이동
 * - /predict 이하: 팀 검색 → 승부예측 페이지(같은 경로 형식)로 이동해 상대팀만 교체
 * - 그 외: 팀 검색 → 팀 프로필로 이동
 */
export default function HeaderSearchBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [showErrorToast, setShowErrorToast] = useState(false);
  const [loading, setLoading] = useState(false);

  const isPlayerPage = location.pathname.startsWith('/players');
  const isPredictPage = location.pathname.startsWith('/predict');
  const type = isPlayerPage ? 'player' : 'team';

  const triggerErrorToast = (msg) => {
    setErrorMessage(msg);
    setShowErrorToast(true);
    setTimeout(() => setShowErrorToast(false), 3000);
  };

  const handleSearch = async () => {
    const trimmed = searchTerm.trim();

    if (!trimmed) {
      triggerErrorToast('검색어를 입력해 주세요.');
      return;
    }
    if (!isValidFormat(trimmed)) {
      triggerErrorToast(
        `올바른 형식으로 입력해 주세요. ( ex. ${type === 'player' ? '뇽따까리#0208' : '팀명#태그'} )`
      );
      return;
    }

    const [namePart, tagPart] = trimmed.split('#');
    setLoading(true);
    try {
      if (type === 'player') {
        const res = await checkPlayerExists(namePart, tagPart);
        if (!res.exists) {
          triggerErrorToast('존재하지 않는 닉네임입니다.');
          return;
        }
        setSearchTerm('');
        navigate(ROUTES.player(namePart, tagPart));
      } else {
        const res = await checkTeamExists(namePart, tagPart);
        if (!res.exists) {
          triggerErrorToast('존재하지 않는 팀입니다.');
          return;
        }
        setSearchTerm('');
        navigate(isPredictPage ? ROUTES.predict(namePart, tagPart) : ROUTES.team(namePart, tagPart));
      }
    } catch {
      triggerErrorToast('검색 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className="header-search-bar">
      {showErrorToast && <div className="header-search-error-toast">{errorMessage}</div>}
      <input
        className="header-search-input"
        placeholder={type === 'player' ? '닉네임 # 태그' : '팀명 # 태그'}
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="button" className="header-search-btn" onClick={handleSearch} disabled={loading}>
        {loading ? '···' : 'SEARCH'}
      </button>
    </div>
  );
}
