import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

export default function AnalysisSection({ analysis, onMapChange, ourLabel, theirLabel }) {
  const mapData = analysis?.mapInfo;

  return (
    <>
      <RoundInfoBlock data={analysis?.roundInfo} />
      <MapInfoBlock 
        data={mapData} 
        selectedMapId={mapData?.selectedMap}
        onMapChange={onMapChange} 
        combos={mapData?.combos} 
        comboAce={mapData?.comboAce} 
        comboWeakness={mapData?.comboWeakness} 
      />
      <EngagementInfoBlock data={analysis?.engagementInfo} ourLabel={ourLabel} theirLabel={theirLabel} />
    </>
  );
}