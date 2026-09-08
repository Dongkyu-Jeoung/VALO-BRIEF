import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchTeamHeader, fetchTeamProfile } from '../../api/teams';
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
 *
 * 성능 개선(2026-09-07): 팀 로고가 늦게 뜬다는 문제 - fetchTeamProfile 하나가 매치 이력+
 * 상세 10건까지 다 기다려야 응답이 와서(~2.5~3.1s) 로고도 그만큼 늦게 나왔다. fetchTeamHeader
 * (팀 로고/이름/디비전만, ~0.3~0.6s)를 동시에 호출해서 먼저 도착하는 대로 헤더부터 그리고,
 * matchHistory/playerRanking 등 무거운 나머지는 fetchTeamProfile이 채운다(services/
 * team_profile.py의 build_team_header/build_team_profile 참고).
 */
export default function TeamProfilePage() {
  const { teamName, teamTag } = useParams();
  const [header, setHeader] = useState(null);
  const [team, setTeam] = useState(null);

  useEffect(() => {
    let active = true;
    setHeader(null);
    setTeam(null);
    fetchTeamHeader(teamName, teamTag).then((data) => { if (active) setHeader(data); });
    fetchTeamProfile(teamName, teamTag).then((data) => { if (active) setTeam(data); });
    return () => { active = false; };
  }, [teamName, teamTag]);

  // team(전체)이 오면 그걸 우선 쓰고, 아직이면 header(로고 등)만으로라도 먼저 그린다.
  const displayTeam = team ?? header;
  if (!displayTeam) return <LoadingText full />;

  return (
    <div className="page-container">
      <TeamProfileBody team={displayTeam} />
    </div>
  );
}

// filteredHistory(선택된 season/act의 실제 매치)에 roundsWon/roundsLost가 다 있으면
// 그걸로 "최근 N게임 요약"을 직접 계산해 Act 선택에 따라 값이 바뀌게 한다.
// 그 필드가 없는 경우(아직 team_profile.py 연동 전 mock, 예: MyTeamAnalysisPage/StatsTab의
// myTeamStatsMock)는 기존처럼 team.recentSummary(고정값)를 그대로 쓴다 - 하위 호환.
function summarizeMatches(matches, fallback) {
  const hasRounds = matches?.length > 0
    && matches.every((m) => typeof m.roundsWon === 'number' && typeof m.roundsLost === 'number');
  if (!hasRounds) return fallback;

  const wins = matches.filter((m) => m.result === 'win').length;
  const roundsWon = matches.reduce((sum, m) => sum + m.roundsWon, 0);
  const roundsLost = matches.reduce((sum, m) => sum + m.roundsLost, 0);
  return {
    winRate: Math.round((wins / matches.length) * 100),
    wins,
    losses: matches.length - wins,
    avgRoundWin: Math.round((roundsWon / matches.length) * 10) / 10,
    avgRoundLose: Math.round((roundsLost / matches.length) * 10) / 10,
  };
}

export function TeamProfileBody({ team }) {
  // actOptions: team_profile.py가 실제 데이터 기준으로 내려주는 [{season, acts}] (없으면
  // 기존 고정 SEASONS/ACTS로 자동 폴백 - useSeasonActFilter 참고).
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(team.actOptions);
  const filteredHistory = useListFilter(
    team.matchHistory,
    (m) => m.season === season && m.act === act
  );
  const recentSummary = summarizeMatches(filteredHistory, team.recentSummary);
  const isComputedSummary = recentSummary !== team.recentSummary;

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
