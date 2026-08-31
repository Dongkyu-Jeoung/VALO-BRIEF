import { Outlet } from 'react-router-dom';
import MainHeader from '../components/layout/MainHeader';
import UtilHeader from '../components/layout/UtilHeader';
import Footer from '../components/layout/Footer';
import { useAuth } from '../context/AuthContext';

/** 메인페이지(Frame 01) 레이아웃 — 로그인 상태에 따라 헤더만 다르게 표시 */
export default function MainLayout() {
  const { isAuthenticated } = useAuth();
  return (
    <div className="app-frame">
      {isAuthenticated ? <UtilHeader /> : <MainHeader />}
      <Outlet />
      <Footer />
    </div>
  );
}
