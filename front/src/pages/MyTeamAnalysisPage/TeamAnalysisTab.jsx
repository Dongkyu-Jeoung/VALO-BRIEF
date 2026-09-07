import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';
import { mapKey } from '../../utils/gameDataKey';

export default function TeamAnalysisTab({ analysis }) {
  // 초기값을 첫 번째 맵의 id로 설정
  const [selectedMapId, setSelectedMapId] = useState(gameData.maps[0].id);

  // 현재 선택된 맵 메타를 안전하게 탐색
  const currentMapMeta = gameData.maps.find(m => 
    m.id === selectedMapId || 
    m.name === selectedMapId || 
    mapKey(m.name) === mapKey(selectedMapId) ||
    m.id?.toLowerCase() === selectedMapId?.toLowerCase() ||
    m.name?.toLowerCase() === selectedMapId?.toLowerCase()
  ) || gameData.maps[0];
  
  const mapStatsMap = analysis?.mapInfoByMap || {};
  const targetKey = currentMapMeta.id?.toLowerCase();
  const alternativeKey = mapKey(currentMapMeta.name);

  const currentMapStats = 
    mapStatsMap[targetKey] || 
    mapStatsMap[alternativeKey] ||
    mapStatsMap[currentMapMeta.name] || 
    mapStatsMap[currentMapMeta.id] || 
    Object.values(mapStatsMap)[0];

  const handleMapChange = (mapValue) => {
    const found = gameData.maps.find(m => 
      m.id === mapValue || 
      m.name === mapValue ||
      m.name?.toLowerCase() === mapValue?.toLowerCase() ||
      m.id?.toLowerCase() === mapValue?.toLowerCase() ||
      mapKey(m.name) === mapKey(mapValue) ||
      mapKey(m.id) === mapKey(mapValue)
    );

    setSelectedMapId(found ? found.id : mapValue);
  };

  return (
    <AnalysisSection
      analysis={analysis}
      currentMapStats={currentMapStats}
      selectedMapId={selectedMapId}
      mapMeta={currentMapMeta}
      onMapChange={handleMapChange}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}