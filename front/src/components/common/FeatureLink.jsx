import { Link } from 'react-router-dom';

/**
 * to가 있으면 라우트 링크로, onClick만 있으면 버튼(예: 모달 오픈)으로 동작하는
 * 재사용 가능한 링크 컴포넌트. 홈페이지의 pill/배너처럼 "같은 동작, 다른 모양"인
 * 여러 자리에서 함께 씁니다.
 */
export default function FeatureLink({ to, onClick, className = '', children }) {
  if (to) {
    return (
      <Link to={to} className={className}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={onClick}>
      {children}
    </button>
  );
}
