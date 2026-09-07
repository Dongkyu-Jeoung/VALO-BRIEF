import React from 'react';
import EmptyImageBox from '../common/EmptyImageBox';
import { gameData } from '../../constants/gameData';

export default function ComboBlock({ title = '선호 요원 조합', combos = [], ace = [], weakness = [] }) {
  const getAgentId = (keyOrName) => {
    if (!keyOrName) return '';
    const found = gameData.agents.find(a => 
      a.id.toLowerCase() === keyOrName.toLowerCase() || 
      a.name === keyOrName
    );
    return found ? found.id : keyOrName.toLowerCase();
  };

  return (
    <div className="combo-block">
      <div className="combo-block-title">{title}</div>
      {combos?.map((c, idx) => {
        const agentList = c.agents || c.agentList || c.members || c.characters || c.agentNames || Object.values(c).find(val => Array.isArray(val)) || [];

        return (
          <div className="combo-row" key={c.label ? `${c.label}-${idx}` : idx}>
            <span className="combo-label">{c.label}</span>
            <div className="combo-agents">
              {agentList.length > 0 ? agentList.map((agentKey, i) => (
                <EmptyImageBox 
                  className="combo-agent-icon" 
                  folder="agents" 
                  assetKey={getAgentId(agentKey)} 
                  key={i} 
                />
              )) : Array.from({ length: 5 }).map((_, i) => (
                <div className="combo-agent-icon" key={i} />
              ))}
            </div>
            <span className="combo-pct">{c.pct ?? c.winRate ?? 0}%</span>
          </div>
        );
      })}

      <div className="combo-detail-cols">
        <div>
          <div className="combo-detail-title text-win">BEST</div>
          {ace?.map((p, idx) => (
            <div className="combo-detail-row" key={p?.name ? `${p.name}-${idx}` : idx}>
              <span>{p.name}</span>
              <div className="stats-group">
                <b>ACS {p.acs}</b>
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="combo-detail-title text-lose">WORST</div>
          {weakness?.map((p, idx) => (
            <div className="combo-detail-row" key={p?.name ? `${p.name}-${idx}` : idx}>
              <span>{p.name}</span>
              <div className="stats-group">
                <b>FD {p.fd}%</b>
                <span>·</span>
                <b>ACS {p.acs}</b>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}