import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchMyTeamStats, fetchMyTeamAnalysis, fetchMyTeamAiReport } from '../../api/myTeam';
import { myTeamProfileMock } from '../../mocks/myTeam.mock';
import ProfileHeader from '../../components/profile/ProfileHeader';
import RecentSummaryBox from '../../components/profile/RecentSummaryBox';
import FilterTabs from '../../components/common/FilterTabs';
import LoadingText from '../../components/common/LoadingText';
import StatsTab from './StatsTab';
import PlayerAnalysisTab from './PlayerAnalysisTab';
import TeamAnalysisTab from './TeamAnalysisTab';
import AiReportTab from './AiReportTab';
import { useSeasonActFilter } from '../../hooks/useSeasonActFilter';
import { useListFilter } from '../../hooks/useListFilter';

const TABS = ['통계', '개인 분석', '팀 분석', 'AI 리포트'];

/**
 * 우리팀 분석 (Frame 09~13) — 로그인 필요한 페이지.
 * 팀 프로필(BOX1)은 이 상위 컴포넌트에서 한 번만 불러오고,
 * 탭 바디는 각 Tab 컴포넌트가 필요한 데이터를 각자 불러옵니다.
 */
export default function MyTeamAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';
  const { season, setSeason, act, setAct } = useSeasonActFilter();

  const [stats, setStats] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [aiReport, setAiReport] = useState(null);

  // '최근 20게임 전적' 박스가 모든 탭 위에 표시되므로 stats는 탭과 무관하게 항상 불러옵니다.
  useEffect(() => {
    if (!stats) fetchMyTeamStats().then(setStats);
  }, [stats]);

  useEffect(() => {
    if (activeTab === '팀 분석' && !analysis) fetchMyTeamAnalysis().then(setAnalysis);
    if (activeTab === 'AI 리포트' && !aiReport) fetchMyTeamAiReport().then(setAiReport);
  }, [activeTab, analysis, aiReport]);

  const filteredHistory = useListFilter(
    stats?.matchHistory,
    (m) => m.season === season && m.act === act
  );

  return (
    <div className="page-container">
      <ProfileHeader
        type="team"
        name={myTeamProfileMock.name}
        tag={myTeamProfileMock.tag}
        division={myTeamProfileMock.division}
        showSeasonSelect
        season={season}
        onSeasonChange={setSeason}
        act={act}
        onActChange={setAct}
      />

      {stats ? <RecentSummaryBox recentSummary={stats.recentSummary} /> : <LoadingText />}

      <FilterTabs tabs={TABS} activeTab={activeTab} onChange={(tab) => setSearchParams({ tab })} />

      {activeTab === '통계' ? (stats ? <StatsTab stats={stats} matches={filteredHistory} /> : <LoadingText />) : null}
      {activeTab === '개인 분석' ? <PlayerAnalysisTab /> : null}
      {activeTab === '팀 분석' ? (analysis ? <TeamAnalysisTab analysis={analysis} /> : <LoadingText />) : null}
      {activeTab === 'AI 리포트' ? (aiReport ? <AiReportTab report={aiReport} teamName={myTeamProfileMock.name} /> : <LoadingText />) : null}
    </div>
  );
}
