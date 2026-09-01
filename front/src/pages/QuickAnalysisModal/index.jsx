import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchQuickAnalysis } from '../../api/teams';
import EmptyImageBox from '../../components/common/EmptyImageBox';
import MiniRankTable from '../../components/common/MiniRankTable';
import ModalTeamSearchBar from '../../components/search/ModalTeamSearchBar';
import { ratingKey } from '@/utils/ratingKey';
import { ROUTES } from '../../constants/routes';

/**
 * 통합검색에서 '팀명#태그'로 검색했을 때 뜨는 팝업.
 * 사용법: <QuickAnalysisModal teamTag="ASC" onClose={...} />
 */
export default function QuickAnalysisModal({ teamTag, onClose }) {
  const [activeTeamTag, setActiveTeamTag] = useState(teamTag);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setActiveTeamTag(teamTag);
  }, [teamTag]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchQuickAnalysis(activeTeamTag).then((res) => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [activeTeamTag]);

  if (!data) return null;

  return (
    <div className="popup-overlay" onClick={onClose}>
      <div className="popup-card" onClick={(e) => e.stopPropagation()}>
        <div className="popup-head">
          <div className="popup-title-wrap">
            <div className="bolt" />
            <div className="popup-title display">3초 상대 분석 리포트</div>
          </div>
          <button
            type="button"
            className="popup-close-btn"
            onClick={onClose}
            aria-label="팝업 닫기"
          >
            ✕
          </button>
        </div>

        <ModalTeamSearchBar onTeamFound={setActiveTeamTag} />

        <div className={`popup-body ${loading ? 'is-loading' : ''}`.trim()}>
          <div className="p-box">
            <div className="p-box-title"><span className="num">1.</span>상대팀 전적 (최근 5게임)</div>
            <div className="wl-strip">
              {data.recentForm.map((r, i) => (
                <div className={`wl-chip ${r === 'win' ? 'w' : 'l'}`} key={i}>{r === 'win' ? 'W' : 'L'}</div>
              ))}
            </div>

            {/* 상대 팀 전적 하단 지표 */}
            <div className="p-stats-row">
              <div className="stat-item">
                <div className="stat-label">승패</div>
                <div className="stat-value"><span className="win-text">{data.wins}승</span> {data.losses}패</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">승률</div>
                <div className="stat-value win-text">{data.winRate}%</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">평균 라운드 승</div>
                <div className="stat-value">{data.avgRoundWin}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">평균 라운드 패</div>
                <div className="stat-value">{data.avgRoundLose}</div>
              </div>
            </div>
          </div>

          <div className="p-box">
            <div className="p-box-title"><span className="num">2.</span>상대 프리미어 팀 티어</div>
            <div className="tier-row">
              <EmptyImageBox
                className="tier-badge-img"
                folder="rating"
                assetKey={ratingKey(data.tier.division)}
                label={`TIER\nICON\nIMAGE`}
              />
              <div className="tier-info">
                <div className="tdiv">{data.tier.division}</div>
                <div className="trp">{data.tier.rp.toLocaleString()} RP</div>
              </div>
              <div className="barplot-wrap">
                <div className="barplot-track"><div className="barplot-fill" style={{ width: `${100 - data.tier.topPercent}%` }} /></div>
                <span className="barplot-label">상위 {data.tier.topPercent}%</span>
              </div>
            </div>
          </div>

          <div className="p-box">
            {/* [수정] 3. 번호 추가 */}
            <div className="p-box-title"><span className="num">3.</span>상대 팀 개인 순위 (최근 5게임 기준)</div>
            <MiniRankTable players={data.playerRanking} showAdr />
          </div>
        </div>
        
        <Link
          to={ROUTES.team(data.teamName.replace(/\s+/g, '-').toLowerCase(), data.teamTag)}
          className="popup-cta"
          onClick={onClose}
        >
          상세 정보 보기 →
        </Link>
      </div>
    </div>
  );
}