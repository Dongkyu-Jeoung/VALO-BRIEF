import EmptyImageBox from '../common/EmptyImageBox';

export default function PredictBox({
  ourTeam,
  opponentTeam,
  ourWinChance = 0
}) {

  if (!ourTeam || !opponentTeam) {
    return null;
  }

  const theirWinChance = 100 - ourWinChance;
  const isOurWinHigh = ourWinChance >= theirWinChance;

  const total = ourWinChance + theirWinChance;
  const ourBarWidth = total > 0 ? (ourWinChance / total) * 100 : 50;
  const theirBarWidth = total > 0 ? (theirWinChance / total) * 100 : 50;

  return (
    <div className="predict-box">
      {/* 우리팀 영역 */}
      <div className="pv-team">
        <div className="pv-label">우리팀</div>
        <EmptyImageBox
          className="avatar-frame"
          src={ourTeam.logoUrl || ourTeam.icon || ourTeam.teamImage || ourTeam.ratingIconUrl}
          folder="teams"
          assetKey={ourTeam.tag}
          label="TEAM"
        />
        <div className="tname display">{ourTeam.name}</div>
      </div>

      {/* 중앙 예상 승률 및 그래프 영역 */}
      <div className="pv-center">
        <div className="pv-label">예상 승률</div>

        <div className="pv-vs-row">
          <div className="pv-percent-wrapper left">
            <span className={`pv-percent win ${isOurWinHigh ? 'is-high' : 'is-low'}`}>
              {ourWinChance}%
            </span>
          </div>

          <div className="pv-vs-bar">
            <div className="a" style={{ width: `${ourBarWidth}%` }} />
            <div className="b" style={{ width: `${theirBarWidth}%` }} />
          </div>

          <div className="pv-percent-wrapper right">
            <span className={`pv-percent lose ${!isOurWinHigh ? 'is-high' : 'is-low'}`}>
              {theirWinChance}%
            </span>
          </div>
        </div>

        <div className="pv-recent20">
          최근 5 게임 · 우리팀 승률 {ourTeam.avgWinRate20 ?? 0}% / 상대팀 승률 {opponentTeam.avgWinRate20 ?? 0}%
        </div>
      </div>

      {/* 상대팀 영역 */}
      <div className="pv-team">
        <div className="pv-label">상대팀</div>
        <EmptyImageBox
          className="avatar-frame"
          src={opponentTeam.logoUrl || opponentTeam.icon || opponentTeam.teamImage || opponentTeam.ratingIconUrl}
          folder="teams"
          assetKey={opponentTeam.tag}
          label="TEAM"
        />
        <div className="tname display">{opponentTeam.name}</div>
      </div>
    </div>
  );
}