import EmptyImageBox from '../common/EmptyImageBox';
import SelectBox from '../common/SelectBox';
import { ratingKey } from '@/utils/ratingKey';
import { SEASONS, ACTS } from '../../constants/seasons';

/**
 * type: 'player' | 'team'
 * player 모드: nickname, tag, level, title, onRefresh(전적 갱신 버튼)
 * team 모드: name, tag, division, avatarKey(팀 로고 asset key, 기본값 = tag)
 * showSeasonSelect: 시즌/Act 선택박스 표시 여부
 * season/onSeasonChange, act/onActChange: 필터 상태(부모의 useSeasonActFilter에서 전달)
 * seasons/acts: 선택박스 옵션 목록(useSeasonActFilter가 반환하는 값 그대로). 안 넘기면
 * constants/seasons.js의 고정 목록을 씀(백엔드 연동 전 팀 프로필 등).
 * refreshDisabled: 전적갱신 쿨다운 활성화 여부(true면 비활성 스타일)
 */
export default function ProfileHeader({
  type = 'team',
  name,
  tag,
  level,
  title,
  avatarUrl,
  division,
  lastUpdated,
  onRefresh,
  refreshDisabled = false,
  showSeasonSelect = true,
  season,
  onSeasonChange,
  act,
  onActChange,
  seasons = SEASONS,
  acts = ACTS,
  avatarKey,
}) {
  return (
    <div className="profile-card">
      <EmptyImageBox
        src={type === 'player' ? avatarUrl : undefined}
        folder={type === 'team' ? 'teams' : undefined}
        assetKey={type === 'team' ? (avatarKey ?? tag) : undefined}
        label={type === 'player' ? 'AGENT' : `TEAM\nIMAGE`}
        className="avatar-frame"
      />
      <div>
        <div className="profile-name display">
          {name} <span className="tagline">#{tag}</span>
        </div>
        {type === 'player' ? (
          <div className="profile-meta">
            <span>LV. <b>{level}</b></span>
            <span>칭호 <b>{title}</b></span>
          </div>
        ) : (
          <div className="profile-meta">
            <span className="rank-chip">
              <EmptyImageBox
                folder="rating"
                assetKey={ratingKey(division)}
                label={`RATING\nICON`}
                className="rank-icon-img"
              />
              {division}
            </span>
          </div>
        )}
      </div>
      <div className="profile-side">
        {type === 'player' && onRefresh ? (
          <button
            className={`refresh-btn ${refreshDisabled ? 'disabled' : 'active'}`}
            onClick={onRefresh}
            disabled={refreshDisabled}
            type="button"
          >
            ⟳ 전적 갱신 <span className="time">{lastUpdated}</span>
          </button>
        ) : null}
        {showSeasonSelect ? (
          <>
            <SelectBox label={season} options={seasons} value={season} onChange={onSeasonChange} />
            <SelectBox label={act} options={acts} value={act} onChange={onActChange} />
          </>
        ) : null}
      </div>
    </div>
  );
}
