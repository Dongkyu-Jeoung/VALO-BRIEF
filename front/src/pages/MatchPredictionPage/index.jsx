import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchPrediction } from '../../api/prediction';
import PredictBox from '../../components/predict/PredictBox';
import FilterTabs from '../../components/common/FilterTabs';
import { TeamProfileBody } from '../TeamProfilePage';
import { fetchTeamProfile } from '../../api/teams';
import AnalysisTab from './AnalysisTab';
import AiReportTab from './AiReportTab';
import LoadingText from '../../components/common/LoadingText';

const TABS = ['통계', '분석', 'AI 리포트'];

export default function MatchPredictionPage() {
  const { teamName, teamTag } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // [수정] '분석' 대신 TABS[0] 인 '통계'를 디폴트 탭으로 변경
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';

  const [prediction, setPrediction] = useState(null);
  const [opponentTeam, setOpponentTeam] = useState(null);

  useEffect(() => {
    let active = true;
    fetchPrediction(teamName, teamTag).then((data) => { if (active) setPrediction(data); });
    fetchTeamProfile(teamName, teamTag).then((data) => { if (active) setOpponentTeam(data); });
    return () => { active = false; };
  }, [teamName, teamTag]);

  if (!prediction) return <LoadingText full />;

  return (
    <div className="page-container">
      <PredictBox ourTeam={prediction.ourTeam} opponentTeam={prediction.opponentTeam} ourWinChance={prediction.ourWinChance} />

      <FilterTabs tabs={TABS} activeTab={activeTab} onChange={(tab) => setSearchParams({ tab })} />

      {activeTab === '통계' && opponentTeam ? <TeamProfileBody team={opponentTeam} /> : null}
      {activeTab === '분석' ? <AnalysisTab analysis={prediction.analysis} /> : null}
      {activeTab === 'AI 리포트' ? (
        <AiReportTab report={prediction.aiReport} opponentName={prediction.opponentTeam.name} />
      ) : null}
    </div>
  );
}