import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';
import { mapKey } from '../../utils/gameDataKey';

export default function TeamAnalysisTab({ analysis }) {
  const [selectedMapId, setSelectedMapId] = useState(gameData.maps[0].id);

  const currentMapMeta = gameData.maps.find(m => m.id === selectedMapId || m.name === selectedMapId || mapKey(m.name) === mapKey(selectedMapId)) || gameData.maps[0];
  
  const mapStatsMap = analysis?.mapInfoByMap || {};
  const targetKey = currentMapMeta.id?.toLowerCase();
  const alternativeKey = mapKey(currentMapMeta.name);

  const currentMapStats = 
    mapStatsMap[targetKey] || 
    mapStatsMap[alternativeKey] ||
    mapStatsMap[currentMapMeta.name] || 
    mapStatsMap[currentMapMeta.id] || 
    Object.values(mapStatsMap)[0];

  return (
    <AnalysisSection
      analysis={analysis}
      currentMapStats={currentMapStats}
      selectedMapId={selectedMapId}
      onMapChange={(mapValue) => {
        const found = gameData.maps.find(m => 
          m.id === mapValue || 
          m.name === mapValue ||
          m.name?.toLowerCase() === mapValue?.toLowerCase() ||
          mapKey(m.name) === mapKey(mapValue)
        );
        
        if (found) {
          setSelectedMapId(found.id);
        }
      }}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}