import RoundInfoBlock from './RoundInfoBlock';
import MapInfoBlock from './MapInfoBlock';
import EngagementInfoBlock from './EngagementInfoBlock';

export default function AnalysisSection({ analysis, onMapChange, ourLabel, theirLabel }) {
  return (
    <>
      <RoundInfoBlock data={analysis.roundInfo} />
      <MapInfoBlock 
        data={analysis.mapInfo} 
        onMapChange={onMapChange} 
        combos={analysis.combos} 
        comboAce={analysis.comboAce} 
        comboWeakness={analysis.comboWeakness} 
      />
      <EngagementInfoBlock data={analysis.engagementInfo} ourLabel={ourLabel} theirLabel={theirLabel} />
    </>
  );
}