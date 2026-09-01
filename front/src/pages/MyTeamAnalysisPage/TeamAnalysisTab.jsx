import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';

export default function TeamAnalysisTab({ analysis }) {
  const [selectedMap, setSelectedMap] = useState(gameData.maps[0].name);
  const mapInfo = { ...analysis.mapInfoByMap[selectedMap], selectedMap };

  return (
    <AnalysisSection
      analysis={{ ...analysis, mapInfo }}
      onMapChange={setSelectedMap}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}