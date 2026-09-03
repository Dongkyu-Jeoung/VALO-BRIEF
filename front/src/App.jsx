import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './layouts/MainLayout';
import AppLayout from './layouts/AppLayout';
import AuthLayout from './layouts/AuthLayout';
import ProtectedRoute from './components/auth/ProtectedRoute';

import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import PlayerProfilePage from './pages/PlayerProfilePage';
import TeamProfilePage from './pages/TeamProfilePage';
import MatchPredictionPage from './pages/MatchPredictionPage';
import MyTeamAnalysisPage from './pages/MyTeamAnalysisPage';

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<HomePage />} />
      </Route>

      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
      </Route>

      <Route element={<AppLayout />}>
        {/* 개인/팀 프로필은 검색만 하면 누구나 볼 수 있어야 해서 로그인 보호 대상이 아님.
            (로그인 필요한 건 내 팀 관련 기능뿐 - 승부예측/내 팀 분석) */}
        <Route path="/players/:riotId/:tag" element={<PlayerProfilePage />} />
        <Route path="/teams/:teamName/:teamTag" element={<TeamProfilePage />} />
        <Route
          path="/predict/:teamName/:teamTag"
          element={<ProtectedRoute><MatchPredictionPage /></ProtectedRoute>}
        />
        <Route
          path="/my-team"
          element={<ProtectedRoute><MyTeamAnalysisPage /></ProtectedRoute>}
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
