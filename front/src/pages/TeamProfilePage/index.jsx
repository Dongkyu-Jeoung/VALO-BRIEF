import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchTeamProfile } from '../../api/teams';
import { fetchRecentOpponent } from '../../api/prediction';
import ProfileHeader from '../../components/profile/ProfileHeader';
import MiniRankTable from '../../components/common/MiniRankTable';
import MapWinrateList from './MapWinrateList';
import TeamMatchHistoryList from '../../components/match/TeamMatchHistoryList';
import DonutChart from '../../components/common/DonutChart';
import ProgressLoading from '../../components/common/ProgressLoading';
import { useSeasonActFilter } from '../../hooks/useSeasonActFilter';
import { useListFilter } from '../../hooks/useListFilter';
import { useAuth } from '../../context/AuthContext';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../../constants/demoTeam';
import { ROUTES } from '../../constants/routes';

/**
 * 이 페이지의 바디는 승부예측 페이지의 '통계' 탭에서도 그대로 재사용됩니다.
 * (MatchPredictionPage/StatsTab.jsx, MyTeamAnalysisPage/StatsTab.jsx 참고)
 *
 * 2026-09-10: 한 번은 로고만 먼저 뜨게 하는 2단계 로딩(fetchTeamHeader 먼저, fetchTeamProfile
 * 나중)을 시도했었는데, 로고/최근요약만 먼저 뜨고 ACT 선택·매치 목록은 몇 초 뒤에 따로
 * 나타나는 게 부자연스럽다는 피드백을 받았다 - PlayerProfilePage(개인 전적 검색)는 애초에
 * 데이터 전체가 준비된 뒤 한 번에 그리는 방식이라 그쪽과의 일관성을 맞추기로 했다. 그래서
 * fetchTeamProfile 응답 하나만 기다렸다가 전체를 한 번에 그린다(PlayerProfilePage와 동일
 * 패턴) - 응답 자체를 빠르게 만드는 쪽(services/search.py의 존재확인 프리페치, routers/
 * teams.py의 write-through 백그라운드화)으로 성능을 개선한다.
 *
 * 페이지 전체 로딩 화면은 ProgressLoading으로 통일한다(승부예측 페이지와 같은 화면).
 * LoadingText full(스피너 + "불러오는 중...")을 섞어 쓰면 로딩 단계마다 화면이 바뀌어
 * 깜빡여 보이므로 페이지 단위 로딩에는 쓰지 않는다.
 */
export default function TeamProfilePage() {
  const { teamName, teamTag } = useParams();
  const { isAuthenticated } = useAuth();
  const [team, setTeam] = useState(null);

  useEffect(() => {
    let active = true;
    setTeam(null);
    async function resolveTeam() {
      const isDemoLink = teamName === DEMO_TEAM_NAME && teamTag === DEMO_TEAM_TAG;
      if (!isAuthenticated || !isDemoLink) return { name: teamName, tag: teamTag };
      const recent = await fetchRecentOpponent();
      return recent ? { name: recent.teamName, tag: recent.teamTag } : { name: teamName, tag: teamTag };
    }

    resolveTeam().then(({ name, tag }) => {
      fetchTeamProfile(name, tag).then((data) => { if (active) setTeam(data); });
    });

    return () => { active = false; };
  }, [teamName, teamTag, isAuthenticated]);

  if (!team) return <ProgressLoading variant="team" />;

  return (
    <div className="page-container">
      <TeamProfileBody team={team} showPredictCta />
    </div>
  );
}
function summarizeMatches(matches, fallback) {
  const hasRounds = matches?.length > 0
    && matches.every((m) => typeof m.roundsWon === 'number' && typeof m.roundsLost === 'number');
  if (!hasRounds) return fallback;

  const wins = matches.filter((m) => m.result === 'win').length;
  const roundsWon = matches.reduce((sum, m) => sum + m.roundsWon, 0);
  const roundsLost = matches.reduce((sum, m) => sum + m.roundsLost, 0);
  const avgKda = Math.round(
    (matches.reduce((sum, m) => sum + (m.kda ?? 0), 0) / matches.length) * 100
  ) / 100;
  return {
    winRate: Math.round((wins / matches.length) * 100),
    wins,
    losses: matches.length - wins,
    avgRoundWin: Math.round((roundsWon / matches.length) * 10) / 10,
    avgRoundLose: Math.round((roundsLost / matches.length) * 10) / 10,
    avgKda,
  };
}

export function TeamProfileBody({ team, showPredictCta = false }) {
  const { user, isAuthenticated } = useAuth();
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(team.actOptions);
  const filteredHistory = useListFilter(
    team.matchHistory,
    (m) => m.season === season && m.act === act
  );
  const recentSummary = summarizeMatches(filteredHistory, team.recentSummary);
  const isComputedSummary = recentSummary !== team.recentSummary;
  const isOwnTeam = user?.teamName === team.name && user?.teamTag === team.tag;
  const showPredictButton = showPredictCta && isAuthenticated && !isOwnTeam;

  return (
    <>
      <ProfileHeader
        type="team"
        name={team.name}
        tag={team.tag}
        division={team.division}
        avatarUrl={team.ratingIconUrl}
        season={season}
        onSeasonChange={setSeason}
        act={act}
        onActChange={setAct}
        seasons={seasons}
        acts={acts}
        predictTo={showPredictButton ? ROUTES.predict(team.name, team.tag) : undefined}
      />

      <div className="mh-grid">
        <div>
          <div className="mh-box">
            <h5>{isComputedSummary ? `최근 ${filteredHistory.length}게임 요약` : '최근 20게임 요약'}</h5>
            <DonutChart winPct={recentSummary.winRate} />
            <div className="wl-legend">
              <span><span className="dot win" />{recentSummary.wins}승</span>
              <span><span className="dot lose" />{recentSummary.losses}패</span>
            </div>
            <div className="metric-row"><span>평균 라운드 승</span><b>{recentSummary.avgRoundWin}</b></div>
            <div className="metric-row"><span>평균 라운드 패</span><b>{recentSummary.avgRoundLose}</b></div>
            <div className="metric-row"><span>평균 KDA</span><b>{recentSummary.avgKda}</b></div>
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