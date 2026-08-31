import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

/**
 * ★ 핵심 공용 컴포넌트 ★
 * 승부예측(Frame07 분석탭)과 우리팀분석(Frame12 팀분석탭)이 완전히 동일한 구조라서
 * 하나로 통합했습니다. analysis shape만 맞춰서 넘기면 어디서든 재사용 가능합니다.
 *
 * analysis: { roundInfo, mapInfo, engagementInfo } - mocks/prediction.mock.js, mocks/myTeam.mock.js 참고
 */
export default function AnalysisSection({ analysis, onMapChange, ourLabel, theirLabel }) {
  return (
    <>
      <RoundInfoBlock data={analysis.roundInfo} />
      <MapInfoBlock data={analysis.mapInfo} onMapChange={onMapChange} />
      <EngagementInfoBlock data={analysis.engagementInfo} ourLabel={ourLabel} theirLabel={theirLabel} />
    </>
  );
}
