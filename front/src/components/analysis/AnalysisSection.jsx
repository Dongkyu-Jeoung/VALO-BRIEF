import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

/**
 * ③번 블록(교전 정보)은 화면마다 다르다 - 우리팀 분석(MyTeamAnalysisPage)은 실측 통계
 * (EngagementInfoBlock, 기본값)를, 상대팀 검색(MatchPredictionPage)은 AI 예측
 * (EngagementPredictionBlock)을 쓴다(server/승부예측_성능_분석.md 7번 참고). 호출부가
 * EngagementComponent/engagementData를 안 넘기면 예전과 완전히 동일하게 동작한다.
 */
export default function AnalysisSection({
  analysis,
  currentMapStats,
  selectedMapId,
  mapMeta,
  maps,
  onMapChange,
  ourLabel,
  theirLabel,
  EngagementComponent = EngagementInfoBlock,
  engagementData,
}) {
  // 팀원 사망 위치 분석(히트맵)은 선택된 맵 기준 데이터라 currentMapStats
  // (analysis.mapInfoByMap[selectedMapId], services/team_profile.py·my_team_analysis.py
  // 에서 deathLocations로 내려줌)에 들어있다 - engagementInfo 쪽엔 없으므로 여기서 합쳐서
  // EngagementComponent(DeathMapTracker가 기대하는 data.deaths)로 전달한다.
  const engagementDisplayData = {
    ...(engagementData ?? analysis?.engagementInfo),
    deaths: currentMapStats?.deathLocations ?? [],
  };

  return (
    <>
      <RoundInfoBlock data={analysis?.roundInfo} />
      <MapInfoBlock
        data={currentMapStats}
        selectedMapId={selectedMapId}
        mapMeta={mapMeta}
        maps={maps}
        onMapChange={onMapChange}
        combos={currentMapStats?.combos || currentMapStats?.agentCombos}
        comboAce={currentMapStats?.comboAce || currentMapStats?.bestCombo}
        comboWeakness={currentMapStats?.comboWeakness || currentMapStats?.worstCombo}
      />
      <EngagementComponent
        data={engagementDisplayData}
        ourLabel={ourLabel}
        theirLabel={theirLabel}
        selectedMapId={selectedMapId}
      />
    </>
  );
}