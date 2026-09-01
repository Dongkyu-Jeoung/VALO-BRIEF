import { useState } from 'react';
import { checkTeamExists } from '../../api/search';
import '../../styles/components/modal-team-search-bar.css';

const isValidFormat = (input) => /^.+#.+$/.test(input.trim());

/**
 * QuickAnalysisModal 전용 팀 검색창.
 * 모달을 닫지 않고, 검색된 팀의 태그를 onTeamFound로 넘겨 데이터만 교체합니다.
 */
export default function ModalTeamSearchBar({ onTeamFound }) {
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
      triggerErrorToast('올바른 형식으로 입력해 주세요. ( ex. 팀명#태그 )');
      return;
    }

    const [namePart, tagPart] = trimmed.split('#');
    setLoading(true);
    try {
      const res = await checkTeamExists(namePart, tagPart);
      if (!res.exists) {
        triggerErrorToast('존재하지 않는 팀입니다.');
        return;
      }
      setSearchTerm('');
      onTeamFound(tagPart);
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
