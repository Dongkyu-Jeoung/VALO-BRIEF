import { gameData } from '../../constants/gameData';

export default function AgentsList() {
  return (
    <div className="analysis-row">
      <div className="analysis-row-head">
        <h5>요원 목록</h5>
      </div>
      <div className="agent-list-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: '10px' }}>
        {gameData.agents.map((agent) => (
          <div key={agent.id} className="agent-card" style={{ textAlign: 'center' }}>
            <img 
              src={agent.image} 
              alt={agent.name} 
              style={{ width: '60px', height: '60px', objectFit: 'contain' }} 
            />
            <div style={{ marginTop: '5px', fontSize: '13px' }}>{agent.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}