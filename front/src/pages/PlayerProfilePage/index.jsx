import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchPlayerProfile } from '../../api/players';
import ProfileHeader from '../../components/profile/ProfileHeader';
import ModeStatCards from './ModeStatCards';
import RoleDistribution from './RoleDistribution';
import TopAgentsList from './TopAgentsList';
import MatchHistoryList from '../../components/match/MatchHistoryList';
import DonutChart from '../../components/common/DonutChart';
import LoadingText from '../../components/common/LoadingText';
import { useSeasonActFilter } from '../../hooks/useSeasonActFilter';
import { useListFilter } from '../../hooks/useListFilter';
import { useCooldown } from '../../hooks/useCooldown';
import { MODES } from '../../constants/modes';

export default function PlayerProfilePage() {
  const { riotId, tag } = useParams();
  const [profile, setProfile] = useState(null);
  const [mode, setMode] = useState('전체');
  const { season, setSeason, act, setAct } = useSeasonActFilter();
  const { isReady, trigger } = useCooldown(`${riotId}-${tag}`);

  useEffect(() => {
    let active = true;
    fetchPlayerProfile(riotId, tag).then((data) => {
      if (active) setProfile(data);
    });
    return () => { active = false; };
  }, [riotId, tag]);

  const filteredHistory = useListFilter(
    profile?.matchHistory,
    (m) => (mode === '전체' || m.mode === mode) && m.season === season && m.act === act
  );

  if (!profile) return <LoadingText />;

  function handleRefresh() {
    trigger();
    fetchPlayerProfile(riotId, tag).then(setProfile);
  }

  return (
    <div className="page-container">
      <ProfileHeader
        type="player"
        name={profile.nickname}
        tag={profile.tag}
        level={profile.level}
        title={profile.title}
        lastUpdated={profile.lastUpdated}
        onRefresh={handleRefresh}
        refreshDisabled={!isReady}
        season={season}
        onSeasonChange={setSeason}
        act={act}
        onActChange={setAct}
      />

      <div className="mode-tabs">
        {MODES.map((m) => (
          <div
            key={m}
            className={`mode-tab ${mode === m ? 'on' : ''}`.trim()}
            onClick={() => setMode(m)}
          >
            {m}
          </div>
        ))}
      </div>

      <ModeStatCards modeStats={profile.modeStats} />

      <div className="mh-grid">
        <div>
          <div className="mh-box">
            <h5>최근 20게임 요약</h5>
            <DonutChart winPct={profile.recentSummary.winRate} />
            <div className="wl-legend">
              <span><span className="dot win" />{profile.recentSummary.wins}승</span>
              <span><span className="dot lose" />{profile.recentSummary.losses}패</span>
            </div>
            <div className="metric-row"><span>평균 K/D</span><b>{profile.recentSummary.avgKd}</b></div>
            <div className="metric-row"><span>평균 ADR</span><b>{profile.recentSummary.avgAdr}</b></div>
          </div>
          <RoleDistribution roles={profile.roleDistribution} />
          <TopAgentsList agents={profile.topAgents} />
        </div>

        <MatchHistoryList matches={filteredHistory} total={20} />
      </div>
    </div>
  );
}
