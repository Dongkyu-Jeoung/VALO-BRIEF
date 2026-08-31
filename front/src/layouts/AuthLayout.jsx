import { Link, Outlet, useLocation } from 'react-router-dom';
import Logo from '../components/layout/Logo';
import { getAsset } from '@/assets';

/**
 * 로그인/회원가입 공용 레이아웃.
 * Figma(login.png, signup.png) 기준: 카드 없이 전체화면 배경 이미지 위에 폼이 바로 떠있는 구조.
 * src/assets/images/auth/login.png, signup.png 를 넣으면 자동으로 배경이 채워집니다.
 */
export default function AuthLayout() {
  const { pathname } = useLocation();
  const bgKey = pathname.startsWith('/signup') ? 'signup' : 'login';
  const bgImage = getAsset('auth', bgKey);

  return (
    <div
      className="auth-page"
      style={bgImage ? { backgroundImage: `url(${bgImage})` } : undefined}
    >
      <header className="auth-page-header">
        <Link to="/"><Logo /></Link>
      </header>
      <div className="auth-page-body">
        <Outlet />
      </div>
    </div>
  );
}
