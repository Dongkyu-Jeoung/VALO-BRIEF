import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchTeamAnalysis, fetchTeamProfile } from '../../api/teams';
import { fetchPrediction, fetchRecentOpponent } from '../../api/prediction';
import { FORCE_MOCK_PREDICTION } from '../../api/config';
import { teamProfileMock } from '../../mocks/team.mock';
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
    // 로그인 후: 상대팀을 우리 팀의 "가장 최근에 매치했던 팀"으로 자동 설정한다 - 최근
    // 상대를 못 찾으면(매치 이력 없음 등) URL의 팀으로 그냥 둔다.
    async function resolveOpponent() {
      if (!isAuthenticated) return { teamName, teamTag };
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
      // FORCE_MOCK_PREDICTION(api/config.js) - 승부예측 페이지 전체를 백엔드 성능 개선
      // 전까지 임시로 mock만 쓰게 한다(fetchTeamProfile은 TeamProfilePage와 공유하는
      // 함수라 여기서 직접 건드리지 않고, 이 페이지에서만 호출을 건너뛴다).
      if (FORCE_MOCK_PREDICTION) {
        if (active) setOpponentTeam(teamProfileMock);
      } else {
        fetchTeamProfile(name, tag).then((data) => { if (active) setOpponentTeam(data); });
      }
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