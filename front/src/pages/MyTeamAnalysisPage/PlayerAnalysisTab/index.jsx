import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchMyTeamPlayers, fetchMyTeamPlayerDetail } from '../../../api/myTeam';
import PlayerListView from './PlayerListView';
import PlayerDetailView from './PlayerDetailView';
import LoadingText from '../../../components/common/LoadingText';
import { useCooldown } from '../../../hooks/useCooldown';

export default function PlayerAnalysisTab() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [players, setPlayers] = useState(null);
  const [detail, setDetail] = useState(null);
  // 로스터(Henrik member 목록)는 서버가 team_id 기준으로 무기한 캐싱한다(속도 우선,
  // services/my_team_players.py 참고) - 그래서 신규 영입/방출 반영용으로 새로고침
  // 버튼을 두고, 스팸 방지용 쿨다운은 ProfileHeader의 "전적 갱신"과 동일한 훅을 쓴다.
  const { isReady, trigger } = useCooldown('my-team-roster');

  // URL 쿼리 파라미터에서 선택된 선수 ID를 읽어옴
  const selectedId = searchParams.get('playerId');

  useEffect(() => {
    fetchMyTeamPlayers().then(setPlayers);
  }, []);

  function handleRosterRefresh() {
    trigger();
    fetchMyTeamPlayers(true).then(setPlayers);
  }

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

  return (
    <>
      <div className="roster-refresh-row">
        <button
          className={`refresh-btn ${isReady ? 'active' : 'disabled'}`}
          onClick={handleRosterRefresh}
          disabled={!isReady}
          type="button"
        >
          ⟳ 로스터 새로고침
        </button>
      </div>
      <PlayerListView players={players} selectedId={selectedId} onSelect={handleSelect} />
    </>
  );
}