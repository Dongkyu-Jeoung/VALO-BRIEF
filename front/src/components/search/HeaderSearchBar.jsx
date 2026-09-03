import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useExistenceSearch } from '../../hooks/useExistenceSearch';
import { ROUTES } from '../../constants/routes';
import '../../styles/components/header-search-bar.css';

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
  const { checkExists, loading, errorMessage, showErrorToast } = useExistenceSearch();

  const isPlayerPage = location.pathname.startsWith('/players');
  const isPredictPage = location.pathname.startsWith('/predict');
  const type = isPlayerPage ? 'player' : 'team';

  const handleSearch = async () => {
    const found = await checkExists(searchTerm, type);
    if (!found) return;
    setSearchTerm('');
    if (type === 'player') {
      navigate(ROUTES.player(found.namePart, found.tagPart));
    } else {
      navigate(isPredictPage ? ROUTES.predict(found.namePart, found.tagPart) : ROUTES.team(found.namePart, found.tagPart));
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
