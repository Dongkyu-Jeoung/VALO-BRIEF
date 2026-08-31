import { Outlet } from 'react-router-dom';
import UtilHeader from '../components/layout/UtilHeader';
import Footer from '../components/layout/Footer';

/** 로그인 이후 대부분의 페이지가 쓰는 공통 레이아웃 */
export default function AppLayout() {
  return (
    <div className="app-frame">
      <UtilHeader />
      <div className="page-body">
        <Outlet />
      </div>
      <Footer />
    </div>
  );
}
