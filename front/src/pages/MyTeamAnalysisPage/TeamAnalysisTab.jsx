import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';

export default function TeamAnalysisTab({ analysis }) {
  // 이름 대신 맵의 ID(id)를 상태로 관리하도록 수정
  const [selectedMapId, setSelectedMapId] = useState(gameData.maps[0].id);

  // 선택된 ID에 해당하는 맵 메타 정보와 통계 데이터 추출
  const currentMapMeta = gameData.maps.find(m => m.id === selectedMapId) || gameData.maps[0];
  const currentMapStats = analysis?.mapInfoByMap?.[currentMapMeta.name];

  return (
    <AnalysisSection
      analysis={analysis}
      currentMapStats={currentMapStats}
      selectedMapId={selectedMapId}
      onMapChange={setSelectedMapId}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}