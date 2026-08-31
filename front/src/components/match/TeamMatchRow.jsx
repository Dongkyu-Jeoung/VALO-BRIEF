import EmptyImageBox from '../common/EmptyImageBox';

export default function TeamMatchRow({ match }) {
  const isWin = match.result === 'win';
  return (
    <div className={`team-match-row ${isWin ? '' : 'lose'}`}>
      <div className="tm-line1">
        <EmptyImageBox className="tm-map-thumb" folder="maps" assetKey={match.map} label="" />
        <b>{match.map}</b> · {isWin ? 'Win' : 'Lose'} · {match.date} · {match.time} · 라운드{' '}
        <b className={isWin ? 'text-win' : 'text-lose'}>{match.roundScore}</b>
      </div>
      <div className="tm-stat-grid">
        <div className="tm-stat-item"><div className="lbl">KDA</div><b>{match.kda}</b></div>
        <div className="tm-stat-item"><div className="lbl">ADR</div><b>{match.adr}</b></div>
        <div className="tm-stat-item"><div className="lbl">ACS</div><b>{match.acs}</b></div>
        <div className="tm-stat-item"><div className="lbl">퍼블</div><b>{match.firstBlood}</b></div>
      </div>
      <div className="tm-mvp">
        <span className="mvp-tag">MVP</span>
        <EmptyImageBox className="mvp-agent-thumb" folder="agents" assetKey={match.mvp.agent} label="" />
        <span className="mvp-agent-name">{match.mvp.agent}</span>
        <span className="mvp-player">{match.mvp.player}</span>
        <span className="mvp-rest">
          KDA {match.mvp.kda} · 헤드샷 {match.mvp.hs}% · ACS {match.mvp.acs}
        </span>
      </div>
    </div>
  );
}