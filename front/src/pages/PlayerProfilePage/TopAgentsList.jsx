import EmptyImageBox from '../../components/common/EmptyImageBox';

export default function TopAgentsList({ agents }) {
  return (
    <div className="mh-box">
      <h5>즐겨쓰는 요원 TOP 3 <span className="tag">최근 20게임</span></h5>
      {agents.map((a) => (
        <div className="agent-row" key={a.agent}>
          <EmptyImageBox className="agent-thumb" folder="agents" assetKey={a.agent} label="" />
          <div className="agent-info">
            <div className="agent-name">{a.agent}</div>
            <div className="agent-stat-header">K/D | ACS | 승률</div>
            <div className="agent-stat-values">{a.kd} | {a.acs} | {a.winRate}%</div>
          </div>
          <div className="agent-wl"><b>{a.wins}승 {a.losses}패</b></div>
        </div>
      ))}
    </div>
  );
}
