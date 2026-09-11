/** 우리팀 분석 페이지 전용 — 탭 바 위에 위치하는 '최근 N게임 전적' 박스 (Figma: 통계 탭 상단).
 * N은 services/my_team_stats.py::RECENT_SUMMARY_LIMIT(최대 20)이지만 실제 치른 경기가
 * 그보다 적으면(신생 팀 등) 그 경기 수만큼만 집계되므로, 하드코딩 대신 wins+losses 합으로
 * 실제 표본 수를 그대로 보여준다. */
export default function RecentSummaryBox({ recentSummary }) {
  if (!recentSummary) return null;

  const totalGames = (recentSummary.wins ?? 0) + (recentSummary.losses ?? 0);

  return (
    <div className="recent-summary-box">
      <div className="recent-summary-left">
        <div className="recent-summary-pct">{recentSummary.winRate}%</div>
        <div>
          <div className="summary-title">최근 {totalGames}게임 전적</div>
          <div className="summary-wl">
            <span><span className="dot win" />{recentSummary.wins}승</span>
            <span><span className="dot lose" />{recentSummary.losses}패</span>
          </div>
        </div>
      </div>
      <div className="summary-stats">
        <div className="summary-stat"><div className="lbl">평균 라운드 승</div><div className="val">{recentSummary.avgRoundWin}</div></div>
        <div className="summary-stat"><div className="lbl">평균 라운드 패</div><div className="val">{recentSummary.avgRoundLose}</div></div>
      </div>
    </div>
  );
}
