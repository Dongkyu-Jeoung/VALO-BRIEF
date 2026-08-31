export default function RoleDistribution({ roles }) {
  const maxGames = Math.max(...roles.map((r) => r.wins + r.losses));
  return (
    <div className="mh-box">
      <h5>역할군(ROLE) 분포 <span className="tag">최근 20게임</span></h5>
      {roles.map((r) => {
        const games = r.wins + r.losses;
        const widthPct = maxGames ? (games / maxGames) * 100 : 0;
        return (
          <div className="role-row" key={r.role}>
            <span className="role-name">{r.role}</span>
            <div className="role-bar-short"><span style={{ width: `${widthPct}%` }} /></div>
            <span className="role-wl"><b>{r.wins}승 {r.losses}패</b> · {r.winRate}%</span>
          </div>
        );
      })}
    </div>
  );
}
