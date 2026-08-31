/** 우리팀 분석 페이지 전용 — 탭 바 위에 위치하는 '최근 20게임 전적' 박스 (Figma: 통계 탭 상단) */
export default function RecentSummaryBox({ recentSummary }) {
  if (!recentSummary) return null;

  return (
    <div className="recent-summary-box">
      <div className="recent-summary-left">
        <div className="recent-summary-pct">{recentSummary.winRate}%</div>
        <div>
          <div className="summary-title">최근 20게임 전적</div>
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
