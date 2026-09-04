import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';

export default function AnalysisTab({ analysis }) {
  const [selectedMap, setSelectedMap] = useState(gameData.maps[0].name);

  const currentMapObj = gameData.maps.find(m => m.name === selectedMap) || gameData.maps[0];

  const mapKey = Object.keys(analysis?.mapInfoByMap || {}).find(
    key => key.toLowerCase() === currentMapObj.id.toLowerCase()
  );

  const currentMapData = analysis?.mapInfoByMap?.[mapKey] || {
    mapWinRate: 0,
    atkWinRate: 0,
    defWinRate: 0,
    preferredSites: { A: 0, B: 0, center: 0 },
    avgSpikePlantTime: 0,
    matchSample: 0,
    combos: [],
    comboAce: [],
    comboWeakness: []
  };

  const mapInfo = { 
    ...currentMapData, 
    selectedMap: currentMapObj.id,
    mapImage: currentMapObj.image 
  };

  return (
    <AnalysisSection
      analysis={{ ...analysis, mapInfo }}
      currentMapStats={mapInfo} 
      selectedMapId={currentMapObj.name} 
      onMapChange={(mapName) => {
        setSelectedMap(mapName);
      }}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}