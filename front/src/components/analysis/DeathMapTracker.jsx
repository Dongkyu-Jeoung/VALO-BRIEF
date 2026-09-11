import React from 'react';
import { gameData } from '../../constants/gameData';

const DeathMapTracker = ({ selectedMapId, deathData = [] }) => {
  // 선택된 맵의 데이터 찾기
  const currentMap = gameData.maps.find(m => m.id === selectedMapId) || gameData.maps[0];

  return (
    <div className="death-map-wrap">
      {/* 맵 이미지를 감싸는 컨테이너 - 고정 크기 정사각형 */}
      <div className="death-map-box">
        <img src={currentMap.minimap} alt={currentMap.name} />

        {/* 사망 위치 점들 렌더링 (absolute 좌표 이용, 좌표값만 동적이라 인라인 유지) */}
        {deathData.map((death, index) => (
          <div
            key={index}
            className="death-map-dot"
            style={{ left: `${death.x}%`, top: `${death.y}%` }}
            title={`${death.playerName} 사망`}
          />
        ))}
      </div>
    </div>
  );
};

export default DeathMapTracker;