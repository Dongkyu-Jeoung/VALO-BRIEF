import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import Logo from './Logo';
import { useAuth } from '../../context/AuthContext';
import { ROUTES } from '../../constants/routes';

const DEMO_TEAM_NAME = 'team-ascend';
const DEMO_TEAM_TAG = 'ASC';

const NAV_ITEMS = [
  { label: '개인 검색', to: '/players/example/0000' },
  { label: '상대팀 전적 검색', to: ROUTES.team(DEMO_TEAM_NAME, DEMO_TEAM_TAG) },
  { label: '승부 예측', to: ROUTES.predict(DEMO_TEAM_NAME, DEMO_TEAM_TAG) },
  { label: '우리팀 분석', to: ROUTES.myTeam },
];

/** 로그인 이후 공통 유틸 헤더 (Frame 04,06,07,08,09~13) */
export default function UtilHeader() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, logout, user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const userInitial = user?.nickname ? user.nickname.charAt(0) : (user?.username ? user.username.charAt(0) : 'U');

  return (
    <header className="util-header">
      <Link to="/"><Logo size="sm" /></Link>

      <nav className="nav-menu">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            className={location.pathname.startsWith(item.to.split('/').slice(0, 2).join('/')) ? 'on' : ''}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="header-right">
        {isAuthenticated ? (
          <div className="profile-menu">
            <button
              type="button"
              className="profile-avatar-btn"
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="프로필 메뉴"
            >
              <span className="profile-avatar-text">{userInitial}</span>
            </button>
            {menuOpen ? (
              <div className="profile-dropdown">
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    setMenuOpen(false);
                    navigate('/');
                  }}
                >
                  로그아웃
                </button>
              </div>
            ) : null}
          </div>
        ) : (
          <Link to="/login" className="btn-pill">MY</Link>
        )}

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
              {NAV_ITEMS.map((item) => (
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