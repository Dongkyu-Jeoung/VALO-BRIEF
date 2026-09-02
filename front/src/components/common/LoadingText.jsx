// full: 페이지 전체가 이 스피너 하나로만 대체되는 경우(true) - 화면 정중앙에 가깝게 더 크게 표시.
// 이미 렌더된 페이지 안의 한 섹션(카드/탭 등)만 대체하는 경우는 기본값(false)을 쓴다.
export default function LoadingText({ full = false }) {
  return (
    <div className={`loading-state${full ? ' loading-state-full' : ''}`}>
      <span className="loading-spinner" />
      <p className="loading-text">불러오는 중...</p>
    </div>
  );
}
