import { useState } from 'react';
import AnalysisSection from '../../components/analysis/AnalysisSection';
import { gameData } from '../../constants/gameData';

export default function AnalysisTab({ analysis }) {
  const mapInfoMap = analysis?.mapInfoByMap || {};
  const recordedKeys = Object.keys(mapInfoMap);

  // 백엔드에서 0경기 맵이 제거된 mapInfoByMap의 실제 키들만을 기준으로 gameData.maps를 정밀 필터링
  const finalMapList = gameData.maps.filter(m => {
    return recordedKeys.some(key => {
      const cleanKey = key.trim();
      const cleanName = m.name.trim();
      const cleanId = m.id.trim();
      return cleanKey === cleanName || cleanKey === cleanId;
    });
  });

  const validMapList = finalMapList.length > 0 ? finalMapList : [gameData.maps[0]];

  const [selectedMap, setSelectedMap] = useState(validMapList[0].name);

  const currentMapObj = validMapList.find(m => m.name === selectedMap) || validMapList[0];

  const mapKey = recordedKeys.find(
    key => key.trim() === currentMapObj.name.trim() || key.trim() === currentMapObj.id.trim()
  ) || recordedKeys[0];

  const rawMapData = mapInfoMap[mapKey] || {};

  let rawPlantTime = rawMapData.avgSpikePlantTime ?? 0;
  if (typeof rawPlantTime === 'string') {
    rawPlantTime = parseInt(rawPlantTime.replace(/[^0-9]/g, ''), 10) || 0;
  }

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
      maps={validMapList}      
      onMapChange={(mapName) => {
        const foundMap = validMapList.find(m => m.name === mapName);
        if (foundMap) {
          setSelectedMap(mapName);
        }
      }}
      ourLabel="우리팀"
      theirLabel="상대팀"
    />
  );
}