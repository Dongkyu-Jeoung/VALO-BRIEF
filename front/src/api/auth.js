import { httpClient } from './httpClient';
import { ENDPOINTS } from './endpoints';
import { USE_MOCK_ONLY, MOCK_DELAY_MS } from './config';

// 인증은 "실패 시 mock 폴백"이 의미가 없으므로(로그인 성공 여부가 중요) 별도 처리합니다.
// 서버가 없을 때는 더미 로그인(항상 성공)으로 동작합니다.

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function login({ id, password }) {
  if (USE_MOCK_ONLY) {
    console.info('[auth] mock 모드: 서버 없이 더미 로그인 처리');
    return { token: 'mock-token', user: { id, teamName: 'Team Phoenix', teamTag: 'PHX' } };
  }
  return httpClient.post(ENDPOINTS.login(), { id, password });
}

export async function signup(payload) {
  if (USE_MOCK_ONLY) {
    console.info('[auth] mock 모드: 서버 없이 더미 회원가입 처리');
    return { success: true };
  }
  return httpClient.post(ENDPOINTS.signup(), payload);
}

export async function verifyRiotId(payload) {
  if (USE_MOCK_ONLY) {
    await delay(600);
    // 데모/QA용: teamTag를 'FAIL'로 입력하면 인증 실패 상태를 재현할 수 있습니다.
    const verified = payload?.teamTag?.toUpperCase() !== 'FAIL';
    return { verified };
  }
  return httpClient.post(ENDPOINTS.verifyRiotId(), payload);
}

export async function checkIdAvailable(id) {
  if (USE_MOCK_ONLY) {
    await delay(MOCK_DELAY_MS);
    // 데모/QA용: 'taken'을 입력하면 중복 아이디 상태를 재현할 수 있습니다.
    return { available: id !== 'taken' };
  }
  return httpClient.get(ENDPOINTS.checkIdAvailable(id));
}

// 마이페이지 (routers/auth.py: GET/PATCH/DELETE /api/auth/me) - 로그인 상태에서만 호출됨.
// mock 모드에서는 로그인 시 저장해둔 valo_auth_user를 그대로 흉내내서 돌려준다.
function mockTeam() {
  const user = JSON.parse(localStorage.getItem('valo_auth_user') || 'null');
  return {
    teamId: 'mock-team-id',
    email: 'mock@valobrief.com',
    loginId: user?.id || user?.loginId || 'mockuser',
    teamName: user?.teamName || 'Team Phoenix',
    teamTag: user?.teamTag || 'PHX',
    teamImage: null,
    division: null,
    rankingPoints: 0,
    verified: false,
    verifiedAt: null,
    createdAt: new Date().toISOString(),
  };
}

export async function getMe() {
  if (USE_MOCK_ONLY) {
    await delay(MOCK_DELAY_MS);
    return mockTeam();
  }
  return httpClient.get(ENDPOINTS.me());
}

export async function updateMe(payload) {
  if (USE_MOCK_ONLY) {
    await delay(MOCK_DELAY_MS);
    return { ...mockTeam(), ...(payload.email ? { email: payload.email } : {}) };
  }
  return httpClient.patch(ENDPOINTS.me(), payload);
}

export async function deleteMe(password) {
  if (USE_MOCK_ONLY) {
    await delay(MOCK_DELAY_MS);
    return { success: true };
  }
  return httpClient.delete(ENDPOINTS.me(), { password });
}
