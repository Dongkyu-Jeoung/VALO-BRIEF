import { Outlet } from 'react-router-dom';
import MainHeader from '../components/layout/MainHeader';
import UtilHeader from '../components/layout/UtilHeader';
import Footer from '../components/layout/Footer';
import { useAuth } from '../context/AuthContext';

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