import { API_BASE_URL } from './config';

/**
 * 아주 얇은 fetch 래퍼입니다. axios가 필요하면 이 파일만 교체하면 됩니다.
 * 사용하는 쪽(services/*.js)에서는 httpClient.get/post 형태로만 호출하므로
 * 여기 내부 구현이 바뀌어도 나머지 코드는 영향받지 않습니다.
 */
async function request(path, { method = 'GET', body, headers } = {}) {
  const token = localStorage.getItem('valo_auth_token');
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
  delete: (path) => request(path, { method: 'DELETE' }),
};
