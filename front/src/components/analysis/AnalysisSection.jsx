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
        data={engagementData ?? analysis?.engagementInfo}
        ourLabel={ourLabel}
        theirLabel={theirLabel}
        selectedMapId={selectedMapId}
      />
    </>
  );
}