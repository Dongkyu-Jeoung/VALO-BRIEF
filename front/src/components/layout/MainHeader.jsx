import { useState } from 'react';
import { Link } from 'react-router-dom';
import Logo from './Logo';
import { ROUTES } from '../../constants/routes';
import { useAuth } from '../../context/AuthContext';
import { useResolvedNavLinks } from '../../hooks/useResolvedNavLinks';
import NavigationLoading from '../common/NavigationLoading';
import LoadingText from '../common/LoadingText';
import ThemeToggle from '../common/ThemeToggle';

export default function MainHeader() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const { user, isAuthenticated, logout } = useAuth();

  // "개인 검색"/"상대팀 전적 검색"/"승부 예측"은 누른 시점에만 실제 목적지를 조회해서
  // 이동한다(UtilHeader와 동일 패턴 - useResolvedNavLinks 참고, 2026-09-14 재설계).
  const { goToPersonalSearch, goToTeamSearch, goToPredict } = useResolvedNavLinks();
  const menuLinks = [
    { label: '개인 검색', prefix: '/players', onSelect: goToPersonalSearch },
    { label: '상대팀 전적 검색', prefix: '/teams', onSelect: goToTeamSearch },
    { label: '승부 예측', prefix: '/predict', onSelect: goToPredict },
    { label: '우리팀 분석', prefix: ROUTES.myTeam, to: ROUTES.myTeam },
  ];
  // 조회 중인 메뉴 항목 - non-null인 동안 화면 전체를 덮는 로딩 오버레이를 띄운다
  // (UtilHeader와 동일 패턴 - 그쪽 주석 참고). item.prefix로 NavigationLoading에
  // 어떤 문구를 보여줄지 알려줘야 해서 boolean이 아니라 item 자체를 들고 있는다.
  const [resolvingItem, setResolvingItem] = useState(null);

  async function handleSelect(item) {
    if (resolvingItem) return;
    setResolvingItem(item);
    try {
      await item.onSelect();
    } finally {
      setResolvingItem(null);
    }
  }

  const avatarText = user?.nickname ? user.nickname.charAt(0).toUpperCase() : '?';

  const handleLogout = () => {
    logout();
    setDropdownOpen(false);
  };

  return (
    <header className={`site-header ${!isAuthenticated ? 'logged-out' : ''}`}>
      <Link to="/"><Logo /></Link>

      {isAuthenticated && (
        <nav className="nav-menu">
          {menuLinks.map((item) => (
            item.to ? (
              <Link key={item.label} to={item.to}>
                {item.label}
              </Link>
            ) : (
              <a
                key={item.label}
                href={item.prefix}
                onClick={(e) => { e.preventDefault(); handleSelect(item); }}
              >
                {item.label}
              </a>
            )
          ))}
        </nav>
      )}

      {resolvingItem && <NavigationLoading destination={resolvingItem.prefix} />}

      <div className="header-right">
        {isAuthenticated ? (
          <div className="profile-menu">
            <button
              type="button"
              className="profile-avatar-btn"
              title={user?.nickname}
              onClick={() => setDropdownOpen((prev) => !prev)}
            >
              <span className="profile-avatar-img">{avatarText}</span>
            </button>

            {dropdownOpen && (
              <div className="profile-dropdown">
                <button type="button" onClick={handleLogout}>
                  로그아웃
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            <Link to="/login" className="btn-pill">login</Link>
            <Link to="/signup" className="btn-pill">signup</Link>
          </>
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

      {sidebarOpen && (
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
              {menuLinks.map((item) => (
                item.to ? (
                  <Link key={item.label} to={item.to} onClick={() => setSidebarOpen(false)}>
                    {item.label}
                  </Link>
                ) : (
                  <a
                    key={item.label}
                    href={item.prefix}
                    onClick={(e) => { e.preventDefault(); setSidebarOpen(false); handleSelect(item); }}
                  >
                    {item.label}
                  </a>
                )
              ))}
            </div>

            <div className="sidebar-divider" />
            <ThemeToggle />
          </nav>
        </>
      )}
    </header>
  );
}