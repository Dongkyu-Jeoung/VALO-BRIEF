import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchTeamAnalysis, fetchTeamProfile } from '../../api/teams';
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
  
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';

  const [analysisData, setAnalysisData] = useState(null);
  const [opponentTeam, setOpponentTeam] = useState(null);

  useEffect(() => {
    let active = true;
    fetchTeamAnalysis(teamName, teamTag).then((data) => { 
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
    fetchTeamProfile(teamName, teamTag).then((data) => { if (active) setOpponentTeam(data); });
    return () => { active = false; };
  }, [teamName, teamTag]);

  if (!analysisData || !opponentTeam) return <LoadingText full />;

  return (
    <div className="page-container">
      <PredictBox 
        ourTeam={{ name: "우리 팀" }} 
        opponentTeam={opponentTeam} 
        ourWinChance={50} 
      />

      <FilterTabs tabs={TABS} activeTab={activeTab} onChange={(tab) => setSearchParams({ tab })} />

      {activeTab === '통계' && opponentTeam ? <TeamProfileBody team={opponentTeam} /> : null}
      {activeTab === '분석' ? <AnalysisTab analysis={analysisData} /> : null}
      {activeTab === 'AI 리포트' ? (
        <AiReportTab report={null} opponentName={opponentTeam?.name || teamName} />
      ) : null}
    </div>
  );
}