import EmptyImageBox from '../common/EmptyImageBox';
import { agentKey, mapKey } from '../../utils/gameDataKey';

export default function MatchRow({ match }) {
  const isWin = match.result === 'win';
  return (
    <div className={`match-row ${isWin ? '' : 'lose'}`}>
      <div className="match-meta">
        <EmptyImageBox className="match-map-icon" folder="maps" assetKey={mapKey(match.map)} label="" />
        <div>
          <b>{match.mode}</b>
          <span>{match.map}</span>
          <br />
          <span className="match-datetime">{match.date} · {match.time}</span>
        </div>
      </div>
      <div className="match-mid">
        <EmptyImageBox className="match-agent" folder="agents" assetKey={agentKey(match.agent)} label="" />
        <div className="kda-block">
          {match.kills} / {match.deaths} / {match.assists}
          <div className="ratio">KDA {match.kda}</div>
        </div>
        <div className={`round-score ${isWin ? 'win' : 'lose'}`}>
          {match.roundScore}
        </div>
      </div>
      <div className="match-right">
        <div>헤드샷<b>{match.hs}%</b></div>
        <div>ADR<b>{match.adr}</b></div>
        <div>ACS<b>{match.acs}</b></div>
      </div>
      <div className="expand-btn">▾</div>
    </div>
  );
}