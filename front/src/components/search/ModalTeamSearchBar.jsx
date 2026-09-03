import { useState } from 'react';
import { useExistenceSearch } from '../../hooks/useExistenceSearch';
import '../../styles/components/modal-team-search-bar.css';

/**
 * QuickAnalysisModal 전용 팀 검색창.
 * 모달을 닫지 않고, 검색된 팀의 태그를 onTeamFound로 넘겨 데이터만 교체합니다.
 */
export default function ModalTeamSearchBar({ onTeamFound }) {
  const [searchTerm, setSearchTerm] = useState('');
  const { checkExists, loading, errorMessage, showErrorToast } = useExistenceSearch();

  const handleSearch = async () => {
    const found = await checkExists(searchTerm, 'team');
    if (!found) return;
    setSearchTerm('');
    onTeamFound(found.tagPart);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className="modal-search-bar">
      {showErrorToast && <div className="modal-search-error-toast">{errorMessage}</div>}
      <input
        className="modal-search-input"
        placeholder="다른 팀명 # 태그로 다시 조회"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="button" className="modal-search-btn" onClick={handleSearch} disabled={loading}>
        {loading ? '···' : '조회'}
      </button>
    </div>
  );
}
