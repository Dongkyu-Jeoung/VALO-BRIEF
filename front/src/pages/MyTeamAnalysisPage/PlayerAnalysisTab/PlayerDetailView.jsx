import { useState } from 'react';
import StatInlineGrid from '../../../components/common/StatInlineGrid';
import EmptyImageBox from '../../../components/common/EmptyImageBox';
import DuelCompareBar from '../../../components/common/DuelCompareBar';
import DropdownSelect from '../../../components/common/DropdownSelect';
import LineChart from '../../../components/common/LineChart';
import { MAPS } from '../../../constants/maps';

const MAP_OPTIONS = ['전체 맵', ...MAPS];

/** Frame 11 — 선수 상세 (라운드 정보 / 에임 정보 / 교전 정보) */
export default function PlayerDetailView({ player, onBack }) {
  const { aim, engagement } = player;
  const [selectedMap, setSelectedMap] = useState('전체 맵');
  const roundInfo = player.roundInfoByMap[selectedMap];

  return (
    <>
      <div className="user-select">
        👤 <b className="player-name">{player.name} #{player.tag}</b> 선택됨 — <span className="user-select-link" onClick={onBack}>다른 선수 보기 ▾</span>
      </div>

      {/* 라운드 정보 */}
      <div className="analysis-row">
        <div className="analysis-row-head">
          <h5>① 라운드 정보</h5>
          <DropdownSelect icon="🗺" label={selectedMap} options={MAP_OPTIONS} value={selectedMap} onChange={setSelectedMap} />
        </div>
        <div className="subsection-title">공격 / 수비</div>
        <StatInlineGrid
          columns={6}
          items={[
            { label: '공격 K/D', value: roundInfo.atkKd },
            { label: '공격 ACS', value: roundInfo.atkAcs },
            { label: '수비 K/D', value: roundInfo.defKd },
            { label: '수비 ACS', value: roundInfo.defAcs },
            { label: 'FB 비율', value: `${roundInfo.fbPct}%`, sub: '선취 킬' },
            { label: 'FD 비율', value: `${roundInfo.fdPct}%`, sub: '선취 데스' },
          ]}
        />
        <div className="subsection-title">피스톨 / Eco</div>
        <StatInlineGrid
          columns={4}
          items={[
            { label: '피스톨 K/D', value: roundInfo.pistolKd },
            { label: '피스톨 ACS', value: roundInfo.pistolAcs },
            { label: 'Eco K/D', value: roundInfo.ecoKd },
            { label: 'Eco ACS', value: roundInfo.ecoAcs },
          ]}
        />
      </div>

      {/* 에임 관련 정보 */}
      <div className="analysis-row">
        <div className="analysis-row-head"><h5>② 에임 관련 정보</h5></div>
        <div className="subsection-title">타격 비율 · 사용 무기별 스탯</div>
        <div className="aim-dual">
          <div>
            <div className="aim-col-title">타격 비율</div>
            <EmptyImageBox
              className="hitbox-img full"
              folder="hitbox"
              assetKey="default"
              label={`히트박스 이미지\n영역 (부위별 타격률 오버레이)`}
            />
            <div className="hitzone-list">
              {aim.hitzones.map((h) => (
                <div className="hitzone-row" key={h.zone}>
                  {h.zone}
                  <div className="hitzone-bar"><span style={{ width: `${h.pct}%` }} /></div>
                  <b>{h.pct}%</b>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="aim-col-title">사용 무기별 스탯</div>
            {aim.weapons.map((w) => (
              <div className="weapon-row" key={w.name}>
                <EmptyImageBox className="weapon-icon" folder="weapons" assetKey={w.name} label={`${w.name}\nICON`} />
                <div className="weapon-name">{w.name}</div>
                <div className="weapon-stats">
                  <div>K/D<b>{w.kd}</b></div>
                  <div>ADR<b>{w.adr}</b></div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="subsection-title">클러치</div>
        <div className="clutch-row">
          <div className="clutch-chip"><div className="lbl">1v1 성공률</div><div className="val">{aim.clutch['1v1']}%</div></div>
          <div className="clutch-chip"><div className="lbl">1v2 성공률</div><div className="val">{aim.clutch['1v2']}%</div></div>
          <div className="clutch-chip"><div className="lbl">1v3+ 성공률</div><div className="val">{aim.clutch['1v3plus']}%</div></div>
        </div>
      </div>

      {/* 교전 정보 */}
      <div className="analysis-row">
        <div className="analysis-row-head"><h5>③ 교전 정보</h5></div>

        <div className="duel-compare-block">
          <div className="duel-compare-title">트레이드 성공률 (내가 죽었을 때 상대도 죽는지)</div>
          <StatInlineGrid
            columns={2}
            items={[
              { label: '1대1 상황', value: `${engagement.trade1v1}%` },
              { label: '1대2 상황', value: `${engagement.trade1v2}%` },
            ]}
          />
        </div>

        <div className="duel-compare-block">
          <div className="duel-compare-title">스킬 사용 유효율 (스킬명 · 교전 성사율 · 성공률)</div>
          <div className="skill-box-row">
            {engagement.skills.map((s) => (
              <div className="skill-box" key={s.name}>
                <div className="sk-name">{s.name}</div>
                <div className="sk-metrics">
                  <div>교전 성사율<b>{s.engageRate}%</b></div>
                  <div>성공률<b>{s.successRate}%</b></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="duel-compare-block">
          <div className="duel-compare-title">포지션별 상대 비교 (타격대 vs 타격대)</div>
          <DuelCompareBar
            leftLabel={player.name}
            leftPct={engagement.duelistCompare.me}
            rightLabel="상대 타격대"
            rightPct={engagement.duelistCompare.opponent}
          />
        </div>

        <div className="duel-compare-block">
          <div className="duel-compare-title">교전 거리 분포</div>
          <div className="line-chart-wrap">
            <LineChart points={engagement.distanceDistribution} />
          </div>
        </div>
      </div>
    </>
  );
}
