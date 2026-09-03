import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchMyTeamStats, fetchMyTeamAnalysis, fetchMyTeamAiReport } from '../../api/myTeam';
import { myTeamProfileMock } from '../../mocks/myTeam.mock';
import { gameData } from '../../constants/gameData';
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

export default function MyTeamAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';
  const { season, setSeason, act, setAct } = useSeasonActFilter();

  const [stats, setStats] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [aiReport, setAiReport] = useState(null);
  const [selectedMapId, setSelectedMapId] = useState('ascent');

  useEffect(() => {
    if (!stats) fetchMyTeamStats().then(setStats);
    if (!analysis) fetchMyTeamAnalysis().then(setAnalysis);
  }, [stats, analysis]);

  useEffect(() => {
    if (activeTab === 'AI 리포트' && !aiReport) fetchMyTeamAiReport().then(setAiReport);
  }, [activeTab, aiReport]);

  const filteredHistory = useListFilter(
    stats?.matchHistory,
    (m) => m.season === season && m.act === act
  );

  // 최상위에서 현재 선택된 맵의 메타 정보와 통계 데이터를 미리 계산
  const currentMapMeta = gameData.maps.find(m => m.id === selectedMapId) || gameData.maps[0];
  const currentMapStats = analysis?.mapInfoByMap?.[selectedMapId] || null;

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
      
      {/* 팀 분석 탭에 최상위에서 정제한 맵 데이터와 상태 제어 함수를 안전하게 전달 */}
      {activeTab === '팀 분석' ? (
        analysis ? (
          <TeamAnalysisTab 
            analysis={analysis} 
            selectedMapId={selectedMapId}
            currentMapStats={currentMapStats}
            currentMapMeta={currentMapMeta}
            onMapChange={setSelectedMapId} 
          />
        ) : <LoadingText />
      ) : null}

      {activeTab === 'AI 리포트' ? (aiReport ? <AiReportTab report={aiReport} teamName={myTeamProfileMock.name} /> : <LoadingText />) : null}
    </div>
  );
}