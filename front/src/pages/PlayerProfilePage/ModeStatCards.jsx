import EmptyImageBox from '../../components/common/EmptyImageBox';
import { ratingKey } from '@/utils/ratingKey';

const MODE_LABELS = { competitive: '경쟁전', unrated: '일반', swiftplay: '신속 플레이', deathmatch: '데스매치' };

export default function ModeStatCards({ modeStats }) {
  return (
    <div className="stat-grid">
      {Object.entries(modeStats).map(([key, s]) => (
        <div className="stat-card" key={key}>
          <div className="mode-name">
            {MODE_LABELS[key]}
            {key === 'competitive' ? (
              <span className="rank-chip">
                <EmptyImageBox folder="rating" assetKey={ratingKey(s.rank)} label={`RANK\nICON`} className="rank-icon-img" />
                {s.rank}
              </span>
            ) : null}
          </div>
          <div className="stat-rows">
            <div>승률<b>{s.winRate ?? '—'}{s.winRate !== null ? '%' : ''}</b></div>
            <div>헤드샷 %<b>{s.hs}%</b></div>
            <div>K/D<b>{s.kd ?? '—'}</b></div>
            <div>평균 킬<b>{s.avgKills}</b></div>
            <div>평균 딜량<b>{s.adr ?? '—'}</b></div>
            <div>평균 점수<b>{s.acs ?? '—'}</b></div>
          </div>
        </div>
      ))}
    </div>
  );
}
