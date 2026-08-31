import EmptyImageBox from '../common/EmptyImageBox';

export default function PredictBox({ ourTeam, opponentTeam, ourWinChance }) {
  const theirWinChance = 100 - ourWinChance;
  return (
    <div className="predict-box">
      <div className="pv-team">
        <div className="pv-label">우리팀</div>
        <EmptyImageBox className="avatar-frame" folder="teams" assetKey={ourTeam.tag} label="TEAM" />
        <div className="tname display">{ourTeam.name}</div>
      </div>
      <div className="pv-center">
        <div className="pv-label">예상 승률</div>
        <div className="pv-percent win">{ourWinChance}%</div>
        <div className="pv-vs-bar">
          <div className="a" style={{ width: `${ourWinChance}%` }} />
          <div className="b" style={{ width: `${theirWinChance}%` }} />
        </div>
        <div className="pv-percent lose">{theirWinChance}%</div>
        <div className="pv-recent20">
          최근 20게임 · 우리팀 승률 {ourTeam.avgWinRate20}% / 상대팀 승률 {opponentTeam.avgWinRate20}%
        </div>
      </div>
      <div className="pv-team">
        <div className="pv-label">상대팀</div>
        <EmptyImageBox className="avatar-frame" folder="teams" assetKey={opponentTeam.tag} label="TEAM" />
        <div className="tname display">{opponentTeam.name}</div>
      </div>
    </div>
  );
}