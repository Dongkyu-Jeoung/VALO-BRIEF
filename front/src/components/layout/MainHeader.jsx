import { useState } from 'react';
import { Link } from 'react-router-dom';
import Logo from './Logo';
import { ROUTES } from '../../constants/routes';

const DEMO_TEAM_NAME = 'team-ascend';
const DEMO_TEAM_TAG = 'ASC';

const MENU_LINKS = [
  { label: '개인 검색', to: '/players/example/0000' },
  { label: '상대팀 전적 검색', to: ROUTES.team(DEMO_TEAM_NAME, DEMO_TEAM_TAG) },
  { label: '승부 예측', to: ROUTES.predict(DEMO_TEAM_NAME, DEMO_TEAM_TAG) },
  { label: '우리팀 분석', to: ROUTES.myTeam },
];

export default function MainHeader() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <header className="site-header">
      <Link to="/"><Logo /></Link>
      <div className="header-right">
        <Link to="/login" className="btn-pill">login</Link>
        <Link to="/signup" className="btn-pill">signup</Link>
        <button
          type="button"
          className="hamburger"
          aria-label="메뉴 열기"
          aria-expanded={sidebarOpen}
          onClick={() => setSidebarOpen(true)}
        >
          <span /><span /><span />
        </button>
      </div>

      {sidebarOpen ? (
        <>
          <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
          <nav className="sidebar-panel">
            <button
              type="button"
              className="sidebar-close"
              aria-label="메뉴 닫기"
              onClick={() => setSidebarOpen(false)}
            >
              ✕
            </button>
            <div className="sidebar-links">
              {MENU_LINKS.map((item) => (
                <Link key={item.label} to={item.to} onClick={() => setSidebarOpen(false)}>
                  {item.label}
                </Link>
              ))}
            </div>
          </nav>
        </>
      ) : null}
    </header>
  );
}