import EmptyImageBox from '../../components/common/EmptyImageBox';

export default function MapWinrateList({ maps, title = '주요 맵 승률' }) {
  return (
    <div className="mh-box">
      <h5>{title}</h5>
      {maps.map((m) => (
        <div className="map-row" key={m.map}>
          <span className="map-name-cell">
            <EmptyImageBox className="map-thumb" folder="maps" assetKey={m.map} label="" />
            {m.map}
          </span>
          <b>{m.win} / {m.lose}</b>
          <b className={m.winRate >= 60 ? 'hot' : ''}>{m.winRate}%</b>
        </div>
      ))}
    </div>
  );
}
