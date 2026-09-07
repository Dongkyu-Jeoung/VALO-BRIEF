import { createContext, useContext, useState, useCallback, useEffect } from 'react';

const TOKEN_KEY = 'valo_auth_token';
const USER_KEY = 'valo_auth_user';

const AuthContext = createContext(null);

function readUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(() => readUser());

  const applySession = useCallback(({ token: nextToken, user: nextUser }) => {
    if (nextToken) localStorage.setItem(TOKEN_KEY, nextToken);
    if (nextUser) localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setToken(nextToken ?? null);
    setUser(nextUser ?? null);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // httpClient가 저장된 토큰을 실어 보냈는데도 401을 받으면(만료/서명 불일치) 이 이벤트를
  // 쏜다 - 죽은 토큰을 들고 "로그인된 것처럼" 계속 보이는 상태를 막고 즉시 로그아웃시킨다.
  useEffect(() => {
    window.addEventListener('auth:unauthorized', logout);
    return () => window.removeEventListener('auth:unauthorized', logout);
  }, [logout]);

  const value = {
    token,
    user,
    isAuthenticated: !!token,
    applySession,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}