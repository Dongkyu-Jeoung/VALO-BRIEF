import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

export default function AnalysisSection({ analysis, currentMapStats, selectedMapId, onMapChange, ourLabel, theirLabel }) {
  return (
    <>
      <RoundInfoBlock data={analysis?.roundInfo} />
      <MapInfoBlock 
        data={currentMapStats} 
        selectedMapId={selectedMapId}
        onMapChange={onMapChange} 
        combos={currentMapStats?.combos} 
        comboAce={currentMapStats?.comboAce} 
        comboWeakness={currentMapStats?.comboWeakness} 
      />
      <EngagementInfoBlock data={analysis?.engagementInfo} ourLabel={ourLabel} theirLabel={theirLabel} />
    </>
  );
}