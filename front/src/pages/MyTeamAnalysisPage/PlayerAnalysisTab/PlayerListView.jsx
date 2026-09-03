import { useState } from 'react';
import EmptyImageBox from '../../../components/common/EmptyImageBox';
import { gameData } from '../../../constants/gameData';

const SORTABLE_COLUMNS = [
  { key: 'kd', label: 'K/D' },
  { key: 'hs', label: '헤드샷' },
  { key: 'adr', label: 'ADR' },
  { key: 'acs', label: 'ACS' },
];

/** Frame 10 — 선수 리스트 (역할군 제거, 개인 티어 및 모스트 요원 에셋 매핑) */
export default function PlayerListView({ players, selectedId, onSelect }) {
  const [sortKey, setSortKey] = useState('acs');
  const [sortDir, setSortDir] = useState('asc');

  const sorted = [...players].sort((a, b) =>
    sortDir === 'asc' ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]
  );

  function handleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  // gameData.agents 기반 에셋 ID 안전 추출
  function getAgentId(val) {
    if (!val) return '';
    const found = gameData.agents.find(
      (a) => a.id === val || a.name === val || a.id.toLowerCase() === val.toLowerCase()
    );
    return found ? found.id : val.toLowerCase();
  }

  // gameData.tiers.personal 기반 티어 ID 안전 추출
  function getTierId(player) {
    const rawVal = player.tier || player.rank || player.tierName || '';
    if (!rawVal) return 'unrated';

    const found = gameData.tiers.personal.find(
      (t) => t.id === rawVal || t.name === rawVal || t.id.toLowerCase() === rawVal.toLowerCase()
    );
    return found ? found.id : rawVal.toLowerCase();
  }

  return (
    <>
      <div className="user-select">👤 유저 선택 — 목록에서 선수를 눌러 상세 분석 보기 ▾</div>
      
      {/* 상단 헤더: 역할군을 티어로 변경하여 8개 컬럼 구조 일치 */}
      <div className="player-list-head">
        <span>선수</span>
        <span>티어</span>
        <span>MOST AGENT</span>
        {SORTABLE_COLUMNS.map((col) => (
          <span
            key={col.key}
            className="player-list-sort-head"
            onClick={() => handleSort(col.key)}
          >
            {col.label} {sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : ''}
          </span>
        ))}
        <span />
      </div>

      {sorted.map((p) => {
        const isSelected = p.id === selectedId;
        const agentAssetKey = getAgentId(p.mostAgent);
        const tierAssetKey = getTierId(p);

        return (
          <div
            className={`player-row ${isSelected ? 'selected' : ''}`.trim()}
            key={p.id}
            onClick={() => onSelect(p.id)}
          >
            {/* 선수 이름 및 태그 */}
            <div className="player-id-cell">
              <div>
                <div className="pid">{p.name}</div>
                <div className="ptag">#{p.tag}</div>
              </div>
            </div>

            {/* 개인 티어 아이콘 매핑 칸 */}
            <div className="player-tier-cell">
              <EmptyImageBox 
                className="player-tier-icon" 
                folder="tiers" 
                assetKey={tierAssetKey} 
                label="" 
              />
            </div>

            {/* 모스트 요원 이미지 매핑 칸 */}
            <div className="player-agent-cell">
              <EmptyImageBox 
                className="player-agent-thumb" 
                folder="agents" 
                assetKey={agentAssetKey} 
                label="" 
              />
            </div>

            <div className="player-stat-val">{p.kd}</div>
            <div className="player-stat-val">{p.hs}%</div>
            <div className="player-stat-val">{p.adr}</div>
            <div className={`player-stat-val ${isSelected ? 'selected' : ''}`.trim()}>{p.acs}</div>
            <div className="player-row-arrow">→</div>
          </div>
        );
      })}
    </>
  );
}