export default function RoleDistribution({ roles }) {
  
  const totalGames = roles.reduce((sum, r) => sum + (r.wins + r.losses), 0);
  return (
    <div className="mh-box">
      <h5>역할군 분포 <span className="tag">최근 20게임</span></h5>
      {roles.map((r) => {
        const games = r.wins + r.losses;
        // const widthPct = totalGames ? (games / totalGames) * 100 : 0;
        const widthPct = r.winRate;
        return (
          <div className="role-row" key={r.role}>
            <span className="role-name">{r.role}</span>
            <div className="role-bar-short">
              <span style={{ width: `${widthPct}%` }} />
            </div>
            <span className="role-wl"><b>{r.wins}승 {r.losses}패</b> · {r.winRate}%</span>
          </div>
        );
      })}
    </div>
  );
}