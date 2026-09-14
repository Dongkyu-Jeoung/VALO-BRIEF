import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchTeamProfile } from '../../api/teams';
import { fetchRecentOpponent } from '../../api/prediction';
import ProfileHeader from '../../components/profile/ProfileHeader';
import MiniRankTable from '../../components/common/MiniRankTable';
import MapWinrateList from './MapWinrateList';
import TeamMatchHistoryList from '../../components/match/TeamMatchHistoryList';
import DonutChart from '../../components/common/DonutChart';
import LoadingText from '../../components/common/LoadingText';
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
 */
export default function TeamProfilePage() {
  const { teamName, teamTag } = useParams();
  const { isAuthenticated } = useAuth();
  const [team, setTeam] = useState(null);

  useEffect(() => {
    let active = true;
    setTeam(null);

    // 헤더/메뉴의 "상대팀 전적 검색"은 항상 데모 팀(team-ascend#ASC)으로 연결돼 있다.
    // 로그인 상태에서 그 데모 링크로 들어온 경우에만 MatchPredictionPage와 동일한
    // 규칙으로 우리 팀이 가장 최근에 매치했던 상대팀으로 자동 대체한다 - 최근 상대를
    // 못 찾으면(매치 이력 없음 등) URL의 팀으로 그냥 둔다. 헤더 검색으로 실제 팀을
    // 검색해 들어온 경우(URL이 데모 링크가 아님)는 이 자동 대체를 건너뛴다.
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

  if (!team) return <LoadingText full />;

  return (
    <div className="page-container">
      <TeamProfileBody team={team} showPredictCta />
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
  // 팀 전체(5명 합산) KDA - 각 매치 record.kda(services/team_profile.py::_parse_team_match가
  // 이미 5명 합산 kills+assists / 합산 deaths로 계산해둔 값)를 필터링된 매치 수만큼
  // 평균낸다. team.recentSummary.avgKda(백엔드 build_team_profile)와 동일한 정의를
  // Act 필터링 시에도 그대로 유지하기 위함.
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
  // actOptions: team_profile.py가 실제 데이터 기준으로 내려주는 [{season, acts}] (없으면
  // 기존 고정 SEASONS/ACTS로 자동 폴백 - useSeasonActFilter 참고).
  const { user, isAuthenticated } = useAuth();
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(team.actOptions);
  const filteredHistory = useListFilter(
    team.matchHistory,
    (m) => m.season === season && m.act === act
  );
  const recentSummary = summarizeMatches(filteredHistory, team.recentSummary);
  const isComputedSummary = recentSummary !== team.recentSummary;
  // 검색된 팀이 로그인한 내 팀 자신이면(자기 팀 이름으로 검색해 들어온 경우) "승부 예측"은
  // 의미가 없으므로 CTA를 숨긴다.
  const isOwnTeam = user?.teamName === team.name && user?.teamTag === team.tag;
  // 비로그인 상태면 버튼을 아예 숨긴다 - /predict/*가 ProtectedRoute라 눌러도 로그인
  // 페이지로 리다이렉트될 뿐이지만, 그 전에 "누를 수 있는데 로그인 페이지로 튕기는"
  // 어색한 흐름 대신 애초에 안 보이는 쪽이 낫다는 요청(2026-09-14).
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