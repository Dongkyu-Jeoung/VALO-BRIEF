import { API_BASE_URL } from './config';

/**
 * 아주 얇은 fetch 래퍼입니다. axios가 필요하면 이 파일만 교체하면 됩니다.
 * 사용하는 쪽(services/*.js)에서는 httpClient.get/post 형태로만 호출하므로
 * 여기 내부 구현이 바뀌어도 나머지 코드는 영향받지 않습니다.
 *
 * 토큰은 localStorage가 아니라 sessionStorage에 둔다 - 탭을 새로고침해도 남아있지만
 * 탭/브라우저를 완전히 닫으면 사라져서 다음에 열 때 다시 로그인하게 하려는 의도
 * (AuthContext.jsx 참고).
 */
const TOKEN_KEY = 'valo_auth_token';
const REFRESH_TOKEN_KEY = 'valo_auth_refresh_token';

// 여러 요청이 동시에 401을 맞아도 /api/auth/refresh는 한 번만 부르도록 진행 중인
// refresh 호출을 공유한다(안 그러면 요청 수만큼 재발급 호출이 동시에 나감).
let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ refreshToken }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.token) return null;
        sessionStorage.setItem(TOKEN_KEY, data.token);
        return data.token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function request(path, { method = 'GET', body, headers } = {}, isRetry = false) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    // 우리 토큰을 실어 보냈는데도 401이면(access token 만료 등) 로그인 폼의 "비밀번호
    // 오류" 401과 헷갈리지 않게 토큰을 실어 보낸 경우에만 처리한다. 아직 재시도 전이면
    // refresh token으로 access token을 새로 받아 한 번만 재시도하고, 그마저 실패하면
    // (refresh token도 만료/무효) 그때 세션을 완전히 끊는다.
    if (res.status === 401 && token) {
      if (!isRetry) {
        const newToken = await refreshAccessToken();
        if (newToken) {
          return request(path, { method, body, headers }, true);
        }
      }
      // AuthContext가 이 이벤트를 듣고 있다가 sessionStorage/상태를 정리한다.
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    const message = await res.text().catch(() => res.statusText);
    throw new Error(`[HTTP ${res.status}] ${message}`);
  }
  // 204 No Content 등 body 없는 응답 대응
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const httpClient = {
  get: (path) => request(path, { method: 'GET' }),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path, body) => request(path, { method: 'DELETE', body }),
};
