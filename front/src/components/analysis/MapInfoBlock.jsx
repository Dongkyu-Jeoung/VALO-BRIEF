import React from 'react';
import EmptyImageBox from '../common/EmptyImageBox';
import DropdownSelect from '../common/DropdownSelect';
import ComboBlock from './ComboBlock';
import { gameData } from '../../constants/gameData';

export default function MapInfoBlock({ data, selectedMapId, mapMeta, onMapChange }) {
  const currentMapMeta = mapMeta || gameData.maps.find(m => m.id === selectedMapId) || gameData.maps[0];

  const items = [
    { label: '맵 승률', value: `${data?.mapWinRate ?? 0}%` },
    { label: '공격 승률', value: `${data?.atkWinRate ?? 0}%` },
    { label: '수비 승률', value: `${data?.defWinRate ?? 0}%` },
    {
      label: '선호 사이트',
      value: `A ${data?.preferredSites?.A ?? 0}% · B ${data?.preferredSites?.B ?? 0}%`,
      sub: `센터 ${data?.preferredSites?.center ?? 0}%`,
      smallValue: true,
    },
    { 
      label: '평균 스파이크 설치 시간', 
      value: data?.avgSpikePlantTime ?? 0,
      unit: '초'
    },
    { 
      label: '경기 표본', 
      value: data?.matchSample ?? 0,
      unit: '경기'
    },
  ];

  return (
    <div className="analysis-row">
      <div className="analysis-row-head">
        <h5>② 맵 정보</h5>
        <DropdownSelect 
          icon="🗺" 
          label={currentMapMeta?.name} 
          options={gameData.maps.map(m => m.name)} 
          value={currentMapMeta?.name} 
          onChange={(mapName) => {
            if (mapName) onMapChange(mapName);
          }} 
        />
      </div>
      <div className="map-analysis-body">
        <EmptyImageBox
          folder="maps"
          assetKey={currentMapMeta?.id}
          label={`선택한 맵 이미지\n영역 (220×220)`}
          className="map-image-box"
        />
        <div className="stat-inline-grid stat-inline-grid-3">
          {items.map((item) => (
            <div className="stat-inline" key={item.label}>
              <div className="lbl">{item.label}</div>
              <div className={`val ${item.smallValue ? 'sm' : ''}`.trim()}>
                {item.value}
                {item.unit && (
                  <span style={{ 
                    fontFamily: 'var(--font-body)', 
                    fontSize: '14px', 
                    fontWeight: 500, 
                    marginLeft: '3px',
                    color: 'var(--text-2)'
                  }}>
                    {item.unit}
                  </span>
                )}
              </div>
              {item.sub ? <div className="sub">{item.sub}</div> : null}
            </div>
          ))}
        </div>
      </div>
      <ComboBlock combos={data?.combos} ace={data?.comboAce} weakness={data?.comboWeakness} />
    </div>
  );
}