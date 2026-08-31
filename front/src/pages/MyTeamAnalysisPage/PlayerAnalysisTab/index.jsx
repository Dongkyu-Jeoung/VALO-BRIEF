import { useEffect, useState } from 'react';
import { fetchMyTeamPlayers, fetchMyTeamPlayerDetail } from '../../../api/myTeam';
import PlayerListView from './PlayerListView';
import PlayerDetailView from './PlayerDetailView';
import LoadingText from '../../../components/common/LoadingText';

export default function PlayerAnalysisTab() {
  const [players, setPlayers] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [view, setView] = useState('list'); // 'list' | 'detail'

  useEffect(() => {
    fetchMyTeamPlayers().then(setPlayers);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    fetchMyTeamPlayerDetail(selectedId).then(setDetail);
  }, [selectedId]);

  if (!players) return <LoadingText />;

  function handleSelect(id) {
    setSelectedId(id);
    setView('detail');
  }

  // 뒤로가기 후에도 selectedId는 유지 → 목록에서 "마지막으로 선택한 선수"가 계속 표시됩니다.
  function handleBack() {
    setView('list');
  }

  if (view === 'detail') {
    return detail ? <PlayerDetailView player={detail} onBack={handleBack} /> : <LoadingText />;
  }

  return <PlayerListView players={players} selectedId={selectedId} onSelect={handleSelect} />;
}
