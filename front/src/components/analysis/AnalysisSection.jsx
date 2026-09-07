import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

export default function AnalysisSection({ analysis, currentMapStats, selectedMapId, mapMeta, onMapChange, ourLabel, theirLabel }) {
  return (
    <>
      <RoundInfoBlock data={analysis?.roundInfo} />
      <MapInfoBlock 
        data={currentMapStats} 
        selectedMapId={selectedMapId} 
        mapMeta={mapMeta}
        onMapChange={onMapChange} 
        combos={currentMapStats?.combos || currentMapStats?.agentCombos} 
        comboAce={currentMapStats?.comboAce || currentMapStats?.bestCombo} 
        comboWeakness={currentMapStats?.comboWeakness || currentMapStats?.worstCombo} 
      />
      <EngagementInfoBlock data={analysis?.engagementInfo} ourLabel={ourLabel} theirLabel={theirLabel} />
    </>
  );
}