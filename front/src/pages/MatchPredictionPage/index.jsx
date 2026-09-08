import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchTeamAnalysis, fetchTeamProfile } from '../../api/teams';
import { fetchPrediction, fetchRecentOpponent } from '../../api/prediction';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../../constants/demoTeam';
import { useAuth } from '../../context/AuthContext';
import PredictBox from '../../components/predict/PredictBox';
import FilterTabs from '../../components/common/FilterTabs';
import { TeamProfileBody } from '../TeamProfilePage';
import AnalysisTab from './AnalysisTab';
import AiReportTab from './AiReportTab';
import LoadingText from '../../components/common/LoadingText';

const TABS = ['통계', '분석', 'AI 리포트'];

export default function MatchPredictionPage() {
  const { teamName, teamTag } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isAuthenticated } = useAuth();

  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';

  const [analysisData, setAnalysisData] = useState(null);
  const [opponentTeam, setOpponentTeam] = useState(null);
  // 우리팀(로그인한 팀) vs 상대팀 승률 예측 - /api/predict/{team_name}/{team_tag}가
  // JWT로 로그인한 팀을 "우리팀"으로 자동 인식해서 실제 모델(XGBoost)을 돌린다.
  const [prediction, setPrediction] = useState(null);

  useEffect(() => {
    let active = true;

    // 로그인 전: URL의 팀(데모 링크는 실존하지 않는 team-ascend라 자동으로 mock 폴백된다).
    // 로그인 후 + URL이 기본 데모 링크(네비 메뉴/홈 카드가 항상 이 팀으로 연결)일 때만
    // 상대팀을 우리 팀의 "가장 최근에 매치했던 팀"으로 자동 설정한다 - 최근 상대를 못
    // 찾으면(매치 이력 없음 등) URL의 팀으로 그냥 둔다.
    // 헤더 검색창으로 실제 팀을 검색해 들어온 경우(URL이 데모 링크가 아님)는 이 자동
    // 대체를 건너뛰고 검색된 팀을 그대로 존중한다 - 안 그러면 로그인 상태에서 팀을
    // 검색해도 매번 "내 최근 상대팀"으로 덮어써져서 검색한 팀이 안 뜨는 버그가 있었다.
    async function resolveOpponent() {
      const isDemoLink = teamName === DEMO_TEAM_NAME && teamTag === DEMO_TEAM_TAG;
      if (!isAuthenticated || !isDemoLink) return { teamName, teamTag };
      const recent = await fetchRecentOpponent();
      return recent ? { teamName: recent.teamName, teamTag: recent.teamTag } : { teamName, teamTag };
    }

    resolveOpponent().then(({ teamName: name, teamTag: tag }) => {
      if (!active) return;

      fetchTeamAnalysis(name, tag).then((data) => {
        if (active && data) {
          // [안전 매핑] 백엔드 키와 프론트엔드 키 불일치로 인한 undefined 방지
          const normalizedData = {
            ...data,
            roundInfo: {
              attackWinRate: data.roundInfo?.attackWinRate ?? data.roundInfo?.atkWinRate ?? 0,
              defenseWinRate: data.roundInfo?.defenseWinRate ?? data.roundInfo?.defWinRate ?? 0,
              pistolWinRate: data.roundInfo?.pistolWinRate ?? 0,
              ecoWinRate: data.roundInfo?.ecoWinRate ?? 0,
              fbWinRate: data.roundInfo?.fbWinRate ?? 0,
              fdLoseRate: data.roundInfo?.fdLoseRate ?? 0,
            }
          };
          setAnalysisData(normalizedData);
        }
      });
      fetchTeamProfile(name, tag).then((data) => { if (active) setOpponentTeam(data); });
      fetchPrediction(name, tag).then((data) => { if (active) setPrediction(data); });
    });

    return () => { active = false; };
  }, [teamName, teamTag, isAuthenticated]);

  if (!analysisData || !opponentTeam || !prediction) return <LoadingText full />;

  // 로그인 상태인데도 /api/predict가 실패(최근 매치 로스터 5인을 못 찾는 등)해서
  // predictionMock으로 폴백하면 우리팀 이름까지 mock("Team Phoenix")으로 보일 수 있다 -
  // 그 경우에도 이름/태그만큼은 로그인한 팀 정보로 덮어써서 보여준다.
  const ourTeam = user
    ? { ...prediction.ourTeam, name: user.teamName, tag: user.teamTag }
    : prediction.ourTeam;

  return (
    <div className="page-container">
      <PredictBox
        ourTeam={ourTeam}
        opponentTeam={prediction.opponentTeam}
        ourWinChance={prediction.ourWinChance}
      />

      <FilterTabs tabs={TABS} activeTab={activeTab} onChange={(tab) => setSearchParams({ tab })} />

      {activeTab === '통계' && opponentTeam ? <TeamProfileBody team={opponentTeam} /> : null}
      {activeTab === '분석' ? <AnalysisTab analysis={analysisData} /> : null}
      {activeTab === 'AI 리포트' ? (
        <AiReportTab report={prediction.aiReport} opponentName={opponentTeam?.name || teamName} />
      ) : null}
    </div>
  );
}