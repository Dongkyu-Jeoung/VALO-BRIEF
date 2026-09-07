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

  // 기존 맵 데이터 및 요원 조합(combos 등) 유실 방지 복구
  const currentMapData = {
    mapWinRate: rawMapData.mapWinRate ?? 0,
    atkWinRate: rawMapData.attackWinRate ?? 0,
    defWinRate: rawMapData.defenseWinRate ?? 0,
    preferredSites: rawMapData.preferredSites || { A: 0, B: 0, center: 0 },
    avgSpikePlantTime: rawPlantTime,
    matchSample: rawMapData.sampleGames ?? 0,
    combos: rawMapData.combos || [],
    comboAce: rawMapData.comboAce || rawMapData.bestCombo || [],
    comboWeakness: rawMapData.comboWeakness || rawMapData.worstCombo || []
  };

  const mapInfo = { 
    ...currentMapData, 
    selectedMap: currentMapObj.id,
    mapImage: currentMapObj.image 
  };

  const roundInfo = analysis?.roundInfo || {};
  
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
    fbWinRate: safeRoundInfo.fbWinRate,
    fdLoseRate: safeRoundInfo.fdLoseRate,
    fbWin: safeRoundInfo.fbWin,
    fdLose: safeRoundInfo.fdLose,
    fb: safeRoundInfo.fb,
    fd: safeRoundInfo.fd,
    mapInfo
  };

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