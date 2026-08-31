import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { MAPS } from '../../constants/maps';

/** Frame 12 — 승부예측의 AnalysisTab과 완전히 동일한 컴포넌트를 재사용합니다. */
export default function TeamAnalysisTab({ analysis }) {
  const [selectedMap, setSelectedMap] = useState(MAPS[0]);
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
