import { createContext, useContext, useState, useCallback, useEffect } from 'react';

// sessionStorage를 쓰는 이유: 새로고침(F5)에는 살아남지만 탭/브라우저를 완전히 닫으면
// 사라져서 다음에 열 때는 다시 로그인해야 한다 - localStorage를 쓰면 브라우저를 껐다
// 켜도 로그인이 유지돼버려서 요건과 맞지 않았다.
const TOKEN_KEY = 'valo_auth_token';
const REFRESH_TOKEN_KEY = 'valo_auth_refresh_token';
const USER_KEY = 'valo_auth_user';

const AuthContext = createContext(null);

function readUser() {
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(() => readUser());

  const applySession = useCallback(({ token: nextToken, refreshToken: nextRefreshToken, user: nextUser }) => {
    if (nextToken) sessionStorage.setItem(TOKEN_KEY, nextToken);
    if (nextRefreshToken) sessionStorage.setItem(REFRESH_TOKEN_KEY, nextRefreshToken);
    if (nextUser) sessionStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setToken(nextToken ?? null);
    setUser(nextUser ?? null);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
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