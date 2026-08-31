import { useState } from 'react';
import EmptyImageBox from '../../../components/common/EmptyImageBox';

const SORTABLE_COLUMNS = [
  { key: 'kd', label: 'K/D' },
  { key: 'hs', label: '헤드샷' },
  { key: 'adr', label: 'ADR' },
  { key: 'acs', label: 'ACS' },
];

/** Frame 10 — 선수 리스트 (컬럼 정렬 가능, 선택된 선수는 강조 표시) */
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

  return (
    <>
      <div className="user-select">👤 유저 선택 — 목록에서 선수를 눌러 상세 분석 보기 ▾</div>
      <div className="player-list-head">
        <span>선수</span><span>역할군</span><span>MOST AGENT</span>
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
        return (
          <div
            className={`player-row ${isSelected ? 'selected' : ''}`.trim()}
            key={p.id}
            onClick={() => onSelect(p.id)}
          >
            <div className="player-id-cell">
              <EmptyImageBox className="player-avatar" label="" />
              <div>
                <div className="pid">{p.name}</div>
                <div className="ptag">#{p.tag}</div>
              </div>
            </div>
            <div className="player-role-badge">{p.role}</div>
            <div className="player-agent-cell">
              <EmptyImageBox className="player-agent-thumb" folder="agents" assetKey={p.mostAgent} label="" />
              {p.mostAgent}
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
