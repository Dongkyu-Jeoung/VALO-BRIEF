import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchPlayerProfile, fetchPlayerModeStats } from '../../api/players';
import ProfileHeader from '../../components/profile/ProfileHeader';
import ModeStatCards from './ModeStatCards';
import RoleDistribution from './RoleDistribution';
import TopAgentsList from './TopAgentsList';
import MatchHistoryList from '../../components/match/MatchHistoryList';
import DonutChart from '../../components/common/DonutChart';
import LoadingText from '../../components/common/LoadingText';
import ProgressLoading from '../../components/common/ProgressLoading';
import { useSeasonActFilter } from '../../hooks/useSeasonActFilter';
import { useListFilter } from '../../hooks/useListFilter';
import { useCooldown } from '../../hooks/useCooldown';
import { MODES } from '../../constants/modes';

export default function PlayerProfilePage() {
  const { riotId, tag } = useParams();
  const [profile, setProfile] = useState(null);
  const [modeStats, setModeStats] = useState(null);
  const [mode, setMode] = useState('전체');
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(profile?.actOptions);
  const { isReady, trigger } = useCooldown(`${riotId}-${tag}`);

  useEffect(() => {
    let active = true;
    fetchPlayerProfile(riotId, tag).then((data) => {
      if (active) {
        setProfile(data);
        setModeStats(data.modeStats); 
      }
    });
    return () => { active = false; };
  }, [riotId, tag]);

  useEffect(() => {
    if (!profile) return;
    const defaultOption = profile.actOptions?.[0];
    if (defaultOption && season === defaultOption.season && act === defaultOption.acts[0]) {
      setModeStats(profile.modeStats);
      return;
    }
    let active = true;
    fetchPlayerModeStats(riotId, tag, season, act).then((data) => {
      if (active) setModeStats(data);
    });
    return () => { active = false; };
  }, [riotId, tag, season, act, profile]);

  const matchModeFilter = useCallback((m) => mode === '전체' || m.mode === mode, [mode]);
  const filteredHistory = useListFilter(profile?.matchHistory, matchModeFilter);

  if (!profile) return <ProgressLoading variant="player" />;

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
        avatarUrl={profile.avatarUrl}
        lastUpdated={profile.lastUpdated}
        onRefresh={handleRefresh}
        refreshDisabled={!isReady}
        season={season}
        onSeasonChange={setSeason}
        act={act}
        onActChange={setAct}
        seasons={seasons}
        acts={acts}
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

      {modeStats ? <ModeStatCards modeStats={modeStats} /> : <LoadingText />}

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