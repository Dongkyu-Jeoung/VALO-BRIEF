import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { MAPS } from '../../constants/maps';

export default function AnalysisTab({ analysis }) {
  const [selectedMap, setSelectedMap] = useState(MAPS[0]);

  // 실제 연동 시에는 fetchPrediction(teamName, teamTag, { map: selectedMap })처럼
  // 맵을 쿼리 파라미터로 넘겨 서버가 이미 필터링된 단일 맵 데이터를 내려주면 됩니다.
  // 지금은 맵별 mock 데이터(mapInfoByMap)에서 클라이언트가 직접 조회합니다.
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
