import React from 'react';
import EmptyImageBox from '../common/EmptyImageBox';
import DropdownSelect from '../common/DropdownSelect';
import ComboBlock from './ComboBlock';
import { gameData } from '../../constants/gameData';
import { mapKey } from '../../utils/gameDataKey';

export default function MapInfoBlock({ data, selectedMapId, mapMeta, maps, onMapChange }) {

  // 상위에서 넘어온 maps(경기 기록이 있는 맵들)와 gameData.maps를 교집합하여 0경기 맵만 스크롤바에서 제외
  const availableMaps = maps && maps.length > 0 
    ? gameData.maps.filter(m => maps.some(validMap => validMap.id === m.id || validMap.name === m.name))
    : gameData.maps;

  const currentMapMeta = mapMeta || availableMaps.find(m => m.id === selectedMapId) || availableMaps[0];
  const computedAssetKey = mapKey(currentMapMeta?.name) || currentMapMeta?.id?.toLowerCase();

  // 맵마다 사이트 개수가 다르므로(헤이븐/로터스는 A·B·C, 나머지는 A·B) gameData의 sites 목록을 기준으로 표시.
  // 선호 사이트 데이터가 객체(집계 완료)인지 아닌지에 따라 표시.
  // 객체가 아니면(=백엔드가 아직 집계를 못한 경우) 임의의 수치를 지어내지 않고 '데이터 없음'으로 표시.
  const mapSites = currentMapMeta?.sites || ['A', 'B'];
  const siteValue = typeof data?.preferredSite === 'object' && data?.preferredSite !== null
    ? mapSites.map(site => `${site} ${data.preferredSite[site] ?? 0}%`).join(' · ')
    : '데이터 없음';

  const items = [
    { label: '맵 승률', value: `${data?.mapWinRate ?? 0}%` },
    { label: '공격 승률', value: `${data?.atkWinRate ?? 0}%` },
    { label: '수비 승률', value: `${data?.defWinRate ?? 0}%` },
    {
      label: '선호 사이트',
      value: siteValue,
      sub: data?.preferredSite?.center ? `센터 ${data.preferredSite.center}%` : null,
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
          options={availableMaps.map(m => m.name)} 
          value={currentMapMeta?.name} 
          onChange={(mapName) => {
            if (typeof onMapChange === 'function') {
              onMapChange(mapName);
            }
          }} 
        />
      </div>
      <div className="map-analysis-body">
        <EmptyImageBox
          folder="maps"
          assetKey={computedAssetKey}
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
                  <span className="stat-unit">
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