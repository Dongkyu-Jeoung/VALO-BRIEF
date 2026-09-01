import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchPlayerProfile, fetchPlayerModeStats } from '../../api/players';
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
  const [modeStats, setModeStats] = useState(null);
  const [mode, setMode] = useState('전체');
  // actOptions: 백엔드가 실제 데이터 기준으로 내려주는 [{season, acts}] (프로필 로드 전엔 없음)
  const { season, setSeason, act, setAct, seasons, acts } = useSeasonActFilter(profile?.actOptions);
  const { isReady, trigger } = useCooldown(`${riotId}-${tag}`);

  useEffect(() => {
    let active = true;
    fetchPlayerProfile(riotId, tag).then((data) => {
      if (active) {
        setProfile(data);
        setModeStats(data.modeStats); // 기본 선택 Act(actOptions[0]) 스탯은 이미 여기 포함됨
      }
    });
    return () => { active = false; };
  }, [riotId, tag]);

  // 시즌/Act 선택박스 전용 - ModeStatCards만 이 구간 스탯으로 갱신한다.
  // 매치 기록(matchHistory)은 season/act와 무관하게 항상 최근 20게임 그대로 보여준다.
  // 현재 선택이 프로필 응답의 기본 Act와 같으면(최초 로드, 또는 기본 Act로 되돌아온 경우)
  // 이미 갖고 있는 profile.modeStats를 그대로 쓰고 재조회하지 않는다 - 사용자가 실제로
  // 다른 Act를 선택했을 때만 호출한다.
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

  const filteredHistory = useListFilter(
    profile?.matchHistory,
    (m) => mode === '전체' || m.mode === mode
  );

  if (!profile) return <LoadingText />;

  function handleRefresh() {
    trigger();
    fetchPlayerProfile(riotId, tag).then((data) => {
      setProfile(data);
      const defaultOption = data.actOptions?.[0];
      if (defaultOption && season === defaultOption.season && act === defaultOption.acts[0]) {
        setModeStats(data.modeStats);
      } else {
        fetchPlayerModeStats(riotId, tag, season, act).then(setModeStats);
      }
    });
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
