import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchMyTeamPlayers, fetchMyTeamPlayerDetail } from '../../../api/myTeam';
import PlayerListView from './PlayerListView';
import PlayerDetailView from './PlayerDetailView';
import LoadingText from '../../../components/common/LoadingText';

export default function PlayerAnalysisTab() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [players, setPlayers] = useState(null);
  const [detail, setDetail] = useState(null);

  // URL 쿼리 파라미터에서 선택된 선수 ID를 읽어옴
  const selectedId = searchParams.get('playerId');

  useEffect(() => {
    fetchMyTeamPlayers().then(setPlayers);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    fetchMyTeamPlayerDetail(selectedId).then(setDetail);
  }, [selectedId]);

  if (!players) return <LoadingText />;

  const handleSelect = (id) => {
    // 탭 유지 상태에서 URL에 playerId만 추가하여 상세 뷰로 전환
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      newParams.set('playerId', id);
      return newParams;
    });
  };

  const handleBack = () => {
    // playerId만 제거하여 개인 분석 탭 안의 선수 목록으로 복귀
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      newParams.delete('playerId');
      return newParams;
    });
    setDetail(null);
  };

  if (selectedId) {
    return detail ? <PlayerDetailView player={detail} onBack={handleBack} /> : <LoadingText />;
  }

  return <PlayerListView players={players} selectedId={selectedId} onSelect={handleSelect} />;
}