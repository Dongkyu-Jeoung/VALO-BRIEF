import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FaArrowRightFromBracket } from 'react-icons/fa6';
import Logo from './Logo';
import HeaderSearchBar from '../search/HeaderSearchBar';
import { useAuth } from '../../context/AuthContext';
import { useResolvedNavLinks } from '../../hooks/useResolvedNavLinks';
import { ROUTES } from '../../constants/routes';
import LoadingText from '../common/LoadingText';

/** 로그인 이후 공통 유틸 헤더 (Frame 04,06,07,08,09~13) */
export default function UtilHeader() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isHome = location.pathname === '/';

  // "개인 검색"/"상대팀 전적 검색"/"승부 예측"은 누른 시점에만 로그인한 팀 기준 실제
  // 목적지를 조회해서 이동한다(useResolvedNavLinks 참고, 2026-09-14 재설계 - 로그인
  // 할 때마다 자동으로 API를 부르던 이전 방식이 로그인 직후 체감 렉의 원인이었다).
  // prefix는 활성 메뉴 표시(.on)에만 쓰는 정적 라우트 접두사 - 실제 이동 경로는 클릭
  // 시점에 정해지므로 미리 알 수 없다.
  const { goToPersonalSearch, goToTeamSearch, goToPredict } = useResolvedNavLinks();
  const navItems = [
    { label: '개인 검색', prefix: '/players', onSelect: goToPersonalSearch },
    { label: '상대팀 전적 검색', prefix: '/teams', onSelect: goToTeamSearch },
    { label: '승부 예측', prefix: '/predict', onSelect: goToPredict },
    { label: '우리팀 분석', prefix: ROUTES.myTeam, to: ROUTES.myTeam },
  ];
  // 조회 중인지 여부 - true인 동안 화면 전체를 덮는 로딩 오버레이(LoadingText full,
  // PlayerProfilePage/TeamProfilePage가 자체 데이터 로딩에 쓰는 것과 같은 컴포넌트)를
  // 띄운다. 주소는 실제 목적지가 정해졌을 때 딱 한 번만 바뀌므로(useResolvedNavLinks
  // 참고) 중간 경로가 주소창에 노출되는 일은 없다(2026-09-14 정리 - 처음엔 메뉴
  // 항목에만 작은 스피너를 붙였는데 눈에 잘 안 띄고 어색하다는 지적을 받아 전체 화면
  // 오버레이로 바꿨다).
  const [resolving, setResolving] = useState(false);

  async function handleSelect(item) {
    if (resolving) return;
    setResolving(true);
    try {
      await item.onSelect();
    } finally {
      setResolving(false);
    }
  }

  const userInitial = user?.nickname ? user.nickname.charAt(0) : (user?.username ? user.username.charAt(0) : 'U');

  return (
    <header className="util-header">
      <Link to="/"><Logo /></Link>

      <nav className="nav-menu">
        {navItems.map((item) => (
          item.to ? (
            <Link
              key={item.label}
              to={item.to}
              className={location.pathname.startsWith(item.prefix) ? 'on' : ''}
            >
              {item.label}
            </Link>
          ) : (
            <a
              key={item.label}
              href={item.prefix}
              className={location.pathname.startsWith(item.prefix) ? 'on' : ''}
              onClick={(e) => { e.preventDefault(); handleSelect(item); }}
            >
              {item.label}
            </a>
          )
        ))}
      </nav>

      {resolving && <LoadingText full />}

      <div className="header-right">
        {!isHome && <HeaderSearchBar />}

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
              {navItems.map((item) => (
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

            {isAuthenticated ? (
              <div className="sidebar-footer">
                <Link
                  to={ROUTES.myPage}
                  className="sidebar-mypage-btn"
                  onClick={() => setSidebarOpen(false)}
                >
                  마이페이지
                </Link>
                <button
                  type="button"
                  className="sidebar-logout-btn"
                  onClick={() => {
                    logout();
                    setSidebarOpen(false);
                    navigate('/');
                  }}
                >
                  로그아웃
                  <FaArrowRightFromBracket />
                </button>
              </div>
            ) : null}
          </nav>
        </>
      ) : null}
    </header>
  );
}
