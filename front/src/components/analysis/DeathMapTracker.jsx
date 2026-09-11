import React from 'react';
import { gameData } from '../../constants/gameData';
import { useMinimapUrl } from '../../hooks/useMinimapUrls';

const DeathMapTracker = ({ selectedMapId, deathData = [] }) => {
  // 선택된 맵의 데이터 찾기
  const currentMap = gameData.maps.find(m => m.id === selectedMapId) || gameData.maps[0];

  // 좌표 계산(server/services/map_coords_service.py::normalize_location)이 기준으로
  // 삼는 것과 항상 같은 소스(valorant-api.com)의 이미지를 우선 쓴다 - 로컬 이미지가
  // 다른 버전(구도/크롭)이면 좌표는 맞는데 화면에서 벽 위에 찍히는 문제가 있었음
  // (2026-09-11 확인). 아직 못 받아왔거나 서버 요청이 실패하면 기존 로컬 이미지로
  // 그대로 폴백한다.
  const officialMinimapUrl = useMinimapUrl(currentMap.id);
  const minimapSrc = officialMinimapUrl || currentMap.minimap;

  return (
    <div className="death-map-wrap">
      {/* 맵 이미지를 감싸는 컨테이너 - 고정 크기 정사각형 */}
      <div className="death-map-box">
        <img src={minimapSrc} alt={currentMap.name} />

        {/* 사망 위치 마커 렌더링 (absolute 좌표 이용, 좌표값만 동적이라 인라인 유지).
            death-map-dot은 X자 마커(CSS ::before/::after, death-map.css 참고),
            death-map-tooltip은 hover 시 즉시 보이는 커스텀 툴팁. title 속성은 일부러 안
            넣는다 - 커스텀 툴팁과 브라우저 네이티브 title 툴팁이 동시에 겹쳐 뜨는
            문제가 있었음(2026-09-11 확인) - 접근성은 aria-label로 대체. */}
        {deathData.map((death, index) => (
          <div
            key={index}
            className="death-map-dot"
            style={{ left: `${death.x}%`, top: `${death.y}%` }}
            aria-label={`${death.playerName} 사망`}
          >
            <span className="death-map-tooltip">
              {death.playerName}
              {death.deathCount ? ` · ${death.deathCount}회` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DeathMapTracker;