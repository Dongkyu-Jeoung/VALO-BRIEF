import { gameData } from '../../constants/gameData';

export default function WeaponStats() {
  return (
    <div className="profile-section">
      <h4>무기 통계 및 목록</h4>
      <div className="weapon-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '12px' }}>
        {gameData.weapons.map((weapon) => (
          <div key={weapon.id} className="weapon-item" style={{ padding: '10px', border: '1px solid var(--border-color)', borderRadius: '8px', textAlign: 'center' }}>
            <img 
              src={weapon.image} 
              alt={weapon.name} 
              style={{ width: '80px', height: '40px', objectFit: 'contain' }} 
            />
            <div style={{ marginTop: '8px', fontWeight: 600 }}>{weapon.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}