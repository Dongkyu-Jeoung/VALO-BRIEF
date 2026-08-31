import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchTeamProfile } from '../../api/teams';
import ProfileHeader from '../../components/profile/ProfileHeader';
import MiniRankTable from '../../components/common/MiniRankTable';
import MapWinrateList from './MapWinrateList';
import TeamMatchHistoryList from '../../components/match/TeamMatchHistoryList';
import DonutChart from '../../components/common/DonutChart';
import LoadingText from '../../components/common/LoadingText';
import { useSeasonActFilter } from '../../hooks/useSeasonActFilter';
import { useListFilter } from '../../hooks/useListFilter';

/**
 * 이 페이지의 바디는 승부예측 페이지의 '통계' 탭에서도 그대로 재사용됩니다.
 * (MatchPredictionPage/StatsTab.jsx, MyTeamAnalysisPage/StatsTab.jsx 참고)
 */
export default function TeamProfilePage() {
  const { teamName, teamTag } = useParams();
  const [team, setTeam] = useState(null);

  useEffect(() => {
    let active = true;
    fetchTeamProfile(teamName, teamTag).then((data) => { if (active) setTeam(data); });
    return () => { active = false; };
  }, [teamName, teamTag]);

  if (!team) return <LoadingText />;

  return (
    <div className="page-container">
      <TeamProfileBody team={team} />
    </div>
  );
}

export function TeamProfileBody({ team }) {
  const { season, setSeason, act, setAct } = useSeasonActFilter();
  const filteredHistory = useListFilter(
    team.matchHistory,
    (m) => m.season === season && m.act === act
  );

  return (
    <>
      <ProfileHeader
        type="team"
        name={team.name}
        tag={team.tag}
        division={team.division}
        season={season}
        onSeasonChange={setSeason}
        act={act}
        onActChange={setAct}
      />

      <div className="mh-grid">
        <div>
          <div className="mh-box">
            <h5>최근 20게임 요약</h5>
            <DonutChart winPct={team.recentSummary.winRate} />
            <div className="wl-legend">
              <span><span className="dot win" />{team.recentSummary.wins}승</span>
              <span><span className="dot lose" />{team.recentSummary.losses}패</span>
            </div>
            <div className="metric-row"><span>평균 라운드 승</span><b>{team.recentSummary.avgRoundWin}</b></div>
            <div className="metric-row"><span>평균 라운드 패</span><b>{team.recentSummary.avgRoundLose}</b></div>
          </div>
          <div className="mh-box">
            <h5>상대 팀 개인 순위 <span className="tag">최근 5게임</span></h5>
            <MiniRankTable players={team.playerRanking} />
          </div>
          <MapWinrateList maps={team.mapWinrates} />
        </div>

        <TeamMatchHistoryList matches={filteredHistory} total={10} />
      </div>
    </>
  );
}
