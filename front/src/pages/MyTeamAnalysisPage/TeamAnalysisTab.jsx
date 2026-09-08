import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';
import { mapKey } from '../../utils/gameDataKey';

export default function TeamAnalysisTab({ analysis }) {
  const mapStatsMap = analysis?.mapInfoByMap || {};

  // 드롭다운에는 실제 전적(matches/match_player_stats)이 있는 맵만 표시한다 - 데이터가
  // 하나도 없으면(집계 전/매치 없음) 전체 맵 목록으로 폴백해 빈 드롭다운이 되지 않게 한다.
  const playedMapNames = Object.keys(mapStatsMap);
  const availableMaps = playedMapNames.length > 0
    ? gameData.maps.filter(m => playedMapNames.includes(m.name))
    : gameData.maps;

  // 초기값을 실제 전적이 있는 첫 번째 맵의 id로 설정
  const [selectedMapId, setSelectedMapId] = useState(availableMaps[0]?.id ?? gameData.maps[0].id);

  // 현재 선택된 맵 메타를 안전하게 탐색(전적 있는 맵 목록 우선)
  const currentMapMeta = availableMaps.find(m =>
    m.id === selectedMapId ||
    m.name === selectedMapId ||
    mapKey(m.name) === mapKey(selectedMapId) ||
    m.id?.toLowerCase() === selectedMapId?.toLowerCase() ||
    m.name?.toLowerCase() === selectedMapId?.toLowerCase()
  ) || availableMaps[0] || gameData.maps[0];

  const targetKey = currentMapMeta.id?.toLowerCase();
  const alternativeKey = mapKey(currentMapMeta.name);

  const currentMapStats =
    mapStatsMap[targetKey] ||
    mapStatsMap[alternativeKey] ||
    mapStatsMap[currentMapMeta.name] ||
    mapStatsMap[currentMapMeta.id] ||
    Object.values(mapStatsMap)[0];

  const handleMapChange = (mapValue) => {
    const found = availableMaps.find(m =>
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
      maps={availableMaps}
      onMapChange={handleMapChange}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}