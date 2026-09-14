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

  const [stats, setStats] = useState(null);
  // stats.actOptions(백엔드가 실제 전적 기준으로 내려주는 최신 시즌/Act)를 넘겨야
  // useSeasonActFilter가 "실제 전적이 있는 최신 시즌"을 기본값으로 잡는다 - 이걸 안 넘기면
  // 고정 SEASONS/ACTS의 첫 값으로 기본 선택돼, 그 값에 해당하는 전적이 하나도 없을 때
  // "처음엔 아무것도 안 보이다가 Act 셀렉트박스에서 실제 전적 있는 시즌을 직접 골라야만
  // 보이는" 증상이 생긴다(services/my_team_stats.py::build_my_team_stats 참고).
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(stats?.actOptions);
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
      {stats ? (
        <ProfileHeader
          type="team"
          name={stats.name}
          tag={stats.tag}
          division={stats.division}
          avatarUrl={stats.ratingIconUrl}
          showSeasonSelect
          season={season}
          onSeasonChange={setSeason}
          act={act}
          onActChange={setAct}
          seasons={seasons}
          acts={acts}
        />
      ) : (
        <LoadingText />
      )}

      {stats ? <RecentSummaryBox recentSummary={stats.recentSummary} /> : null}

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

      {activeTab === 'AI 리포트' ? (
        aiReport ? (
          <AiReportTab report={aiReport} teamName={stats?.name ?? myTeamProfileMock.name} />
        ) : (
          // AI 리포트는 상대팀과 달리 폴링 없이 이 요청 하나가 끝나야 뜬다(Claude 호출이
          // 요청 안에서 동기로 실행됨 - services/ai_report.py::build_my_team_ai_report 참고,
          // 20~45초 안팎). 그동안 그냥 LoadingText만 보이면 멈춘 것처럼 보여 상대팀 AI리포트
          // (MatchPredictionPage/AiReportTab.jsx의 status==='generating' 안내)와 같은 문구를 넣는다.
          <div className="ai-report-card">
            <div className="popup-head plain">
              <div className="bolt" />
              <div className="popup-title display lg">
                AI 전술 리포트 — {stats?.name ?? myTeamProfileMock.name} 팀 분석
              </div>
            </div>
            <div className="empty-text">
              AI가 우리 팀의 전술 리포트를 생성하고 있습니다. 최대 1분 정도 걸릴 수 있어요.
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}