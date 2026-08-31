/**
 * players: [{ rank, name, acs, hs, position, kd, adr? }]
 * showAdr: ADR 컬럼 표시 여부
 */
export default function MiniRankTable({ players, showAdr = false }) {
  return (
    <table className="mini-table">
      <thead>
        <tr>
          <th>순위</th><th>선수</th><th>ACS</th><th>HS%</th><th>포지션</th><th>K/D</th>
          {showAdr ? <th>ADR</th> : null}
        </tr>
      </thead>
      <tbody>
        {players.map((p) => (
          <tr key={p.rank}>
            <td>{p.rank}</td>
            <td className="name">{p.name}</td>
            <td>{p.acs}</td>
            <td>{p.hs}%</td>
            <td>{p.position}</td>
            <td>{p.kd}</td>
            {showAdr ? <td>{p.adr}</td> : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
