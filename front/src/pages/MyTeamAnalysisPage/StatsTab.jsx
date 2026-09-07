import MiniRankTable from '../../components/common/MiniRankTable';
import MapWinrateList from '../TeamProfilePage/MapWinrateList';
import TeamMatchHistoryList from '../../components/match/TeamMatchHistoryList';

export default function StatsTab({ stats, matches }) {
  return (
    <div className="mh-grid">
      <div>
        <div className="mh-box">
          <h5>팀 개인 순위 <span className="tag">최근 5게임</span></h5>
          <MiniRankTable players={stats.playerRanking} />
        </div>
        <MapWinrateList maps={stats.mapWinrates?.slice(0, 3)} />
      </div>
      <TeamMatchHistoryList matches={matches} total={10} title="팀 매치 히스토리" />
    </div>
  );
}