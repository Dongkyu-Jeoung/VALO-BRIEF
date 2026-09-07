import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';

export default function AnalysisTab({ analysis }) {
  const [selectedMap, setSelectedMap] = useState(gameData.maps[0].name);

  const currentMapObj = gameData.maps.find(m => m.name === selectedMap) || gameData.maps[0];

  const mapKey = Object.keys(analysis?.mapInfoByMap || {}).find(
    key => key.toLowerCase() === currentMapObj.id.toLowerCase() || key === currentMapObj.name
  );

  const rawMapData = analysis?.mapInfoByMap?.[mapKey] || {};

  let rawPlantTime = rawMapData.avgSpikePlantTime ?? 0;
  if (typeof rawPlantTime === 'string') {
    rawPlantTime = parseInt(rawPlantTime.replace(/[^0-9]/g, ''), 10) || 0;
  }

  const currentMapData = {
    mapWinRate: rawMapData.mapWinRate ?? 0,
    atkWinRate: rawMapData.attackWinRate ?? 0,
    defWinRate: rawMapData.defenseWinRate ?? 0,
    preferredSites: { A: 0, B: 0, center: 0 },
    avgSpikePlantTime: rawPlantTime,
    matchSample: rawMapData.sampleGames ?? 0,
    combos: [],
    comboAce: [],
    comboWeakness: []
  };

  const mapInfo = { 
    ...currentMapData, 
    selectedMap: currentMapObj.id,
    mapImage: currentMapObj.image 
  };

  const roundInfo = analysis?.roundInfo || {};
  
  // 퍼스트 블러드 및 디피트 관련 모든 키와 구조를 안전하게 0으로 초기화 및 매핑
  const safeRoundInfo = {
    attackWinRate: roundInfo.attackWinRate ?? 0,
    defenseWinRate: roundInfo.defenseWinRate ?? 0,
    pistolWinRate: roundInfo.pistolWinRate ?? 50,
    ecoWinRate: roundInfo.ecoWinRate ?? 0,
    fbWinRate: roundInfo.fbWinRate ?? 0,
    fdLoseRate: roundInfo.fdLoseRate ?? 0,
    fbWin: roundInfo.fbWin ?? 0,
    fdLose: roundInfo.fdLose ?? 0,
    firstBloodWinRate: roundInfo.firstBloodWinRate ?? 0,
    firstDeathLoseRate: roundInfo.firstDeathLoseRate ?? 0,
    fb: { winRate: 0, loseRate: 0, ...(roundInfo.fb || {}) },
    fd: { winRate: 0, loseRate: 0, ...(roundInfo.fd || {}) },
  };

  const safeAnalysis = {
    ...analysis,
    ...safeRoundInfo,
    roundInfo: safeRoundInfo,
    // 컴포넌트가 최상위 레벨에서 곧바로 참조하는 경우를 위한 방어 속성 주입
    fbWinRate: safeRoundInfo.fbWinRate,
    fdLoseRate: safeRoundInfo.fdLoseRate,
    fbWin: safeRoundInfo.fbWin,
    fdLose: safeRoundInfo.fdLose,
    fb: safeRoundInfo.fb,
    fd: safeRoundInfo.fd,
    mapInfo
  };

  console.log("===== FRONTEND ANALYSIS DATA =====", safeAnalysis);
  return (
    <AnalysisSection
      analysis={safeAnalysis}
      currentMapStats={mapInfo}
      selectedMapId={currentMapObj.id}   
      mapMeta={currentMapObj}           
      onMapChange={(mapName) => {
        setSelectedMap(mapName);
      }}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}