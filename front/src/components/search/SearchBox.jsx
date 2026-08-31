import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { checkPlayerExists, checkTeamExists } from '../../api/search';
import { ROUTES } from '../../constants/routes';

// 이름#태그 형식 검사 (개인/팀 공통)
const isValidFormat = (input) => /^.+#.+$/.test(input.trim());

/**
 * 홈페이지 히어로 검색창과 헤더 통합 검색창에서 공통으로 쓰는 검색 컴포넌트.
 * variant: 'hero' | 'header' — 레이아웃 크기만 다르고 동작은 동일합니다.
 */
export default function SearchBox({ variant = 'hero' }) {
  const navigate = useNavigate();
  const [searchType, setSearchType] = useState('player'); // 'player' | 'team'
  const [searchTerm, setSearchTerm] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [showErrorToast, setShowErrorToast] = useState(false);
  const [loading, setLoading] = useState(false);

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
        `올바른 형식으로 입력해 주세요. ( ex. ${searchType === 'player' ? '뇽따까리#0208' : '팀명#태그'} )`
      );
      return;
    }

    const [namePart, tagPart] = trimmed.split('#');
    setLoading(true);
    try {
      if (searchType === 'player') {
        const res = await checkPlayerExists(namePart, tagPart);
        if (!res.exists) {
          triggerErrorToast('존재하지 않는 닉네임입니다.');
          return;
        }
        navigate(ROUTES.player(namePart, tagPart));
      } else {
        const res = await checkTeamExists(namePart, tagPart);
        if (!res.exists) {
          triggerErrorToast('존재하지 않는 팀입니다.');
          return;
        }
        navigate(ROUTES.team(namePart, tagPart));
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
          placeholder={searchType === 'player' ? '닉네임#태그 (예: 뇽따까리#0208)' : '팀명#태그'}
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
