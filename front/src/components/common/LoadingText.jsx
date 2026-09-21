
export default function LoadingText({ full = false }) {
  return (
    <div className={`loading-state${full ? ' loading-state-full' : ''}`}>
      <span className="loading-spinner" />
      <p className="loading-text">불러오는 중...</p>
    </div>
  );
}