import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import Logo from './Logo';
import SearchBox from '../search/SearchBox';
import EmptyImageBox from '../common/EmptyImageBox';
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
  const { isAuthenticated, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="util-header">
      <Link to="/"><Logo size="sm" /></Link>
      <SearchBox variant="header" />
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
        {isAuthenticated ? (
          <div className="profile-menu">
            <button
              type="button"
              className="profile-avatar-btn"
              onClick={() => setMenuOpen((o) => !o)}
              aria-label="프로필 메뉴"
            >
              <EmptyImageBox className="profile-avatar-img" label="" />
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
          <Link to="/login">MY</Link>
        )}
      </nav>
    </header>
  );
}
