import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useExistenceSearch } from '../../hooks/useExistenceSearch';
import { ROUTES } from '../../constants/routes';
import '../../styles/components/searchbox.css';

/**
 * 홈페이지 히어로 검색창과 헤더 통합 검색창에서 공통으로 쓰는 검색 컴포넌트.
 * variant: 'hero' | 'header' — 레이아웃 크기만 다르고 동작은 동일합니다.
 */
export default function SearchBox({ variant = 'hero' }) {
  const navigate = useNavigate();
  const [searchType, setSearchType] = useState('player'); // 'player' | 'team'
  const [searchTerm, setSearchTerm] = useState('');
  const { checkExists, loading, errorMessage, showErrorToast } = useExistenceSearch();

  const handleSearch = async () => {
    const found = await checkExists(searchTerm, searchType);
    if (!found) return;
    navigate(
      searchType === 'player'
        ? ROUTES.player(found.namePart, found.tagPart)
        : ROUTES.team(found.namePart, found.tagPart)
    );
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className={`search-box search-box-${variant}`}>
      {showErrorToast && <div className="search-error-toast">{errorMessage}</div>}
      <div className="search-type-toggle">
        <button
          type="button"
          className={searchType === 'player' ? 'is-active' : ''}
          onClick={() => setSearchType('player')}
        >
          개인
        </button>
        <button
          type="button"
          className={searchType === 'team' ? 'is-active' : ''}
          onClick={() => setSearchType('team')}
        >
          팀
        </button>
      </div>
      <div className="hero-search-row">
        <input
          className="hero-search-input"
          placeholder={searchType === 'player' ? '닉네임 # 태그 ' : '팀명 # 태그'}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="button" className="btn-search" onClick={handleSearch} disabled={loading}>
          {loading ? '···' : 'SEARCH'}
        </button>
      </div>
    </div>
  );
}
