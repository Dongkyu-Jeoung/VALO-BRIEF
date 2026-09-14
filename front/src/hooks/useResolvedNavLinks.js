import { useNavigate } from 'react-router-dom';
import { fetchMyTeamPlayers } from '../api/myTeam';
import { fetchRecentOpponent } from '../api/prediction';
import { useAuth } from '../context/AuthContext';
import { ROUTES } from '../constants/routes';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../constants/demoTeam';
import { DEMO_PLAYER_NAME, DEMO_PLAYER_TAG } from '../constants/demoPlayer';

export const DEFAULT_PLAYER_LINK = ROUTES.player(DEMO_PLAYER_NAME, DEMO_PLAYER_TAG);
export const DEFAULT_TEAM_LINK = ROUTES.team(DEMO_TEAM_NAME, DEMO_TEAM_TAG);
export const DEFAULT_PREDICT_LINK = ROUTES.predict(DEMO_TEAM_NAME, DEMO_TEAM_TAG);

// 헤더/메뉴바의 "개인 검색"·"상대팀 전적 검색"·"승부 예측"용 핸들러 3개(async).
//
// 2026-09-14 세 번째 설계: 처음엔 로그인 시 자동으로 미리 계산해뒀다가(로그인 렉의
// 원인이었음), 그다음엔 클릭 시 중간 경로(/nav-resolve/:kind)로 먼저 이동시켜 로딩
// 화면을 보여준 뒤 최종 경로로 교체 이동했는데, 그러면 그 중간 경로가 주소창에 잠깐
// 그대로 노출된다는 지적을 받았다. 이제는 주소는 전혀 바꾸지 않고, 호출부(MainHeader/
// UtilHeader)가 이 함수들이 반환하는 Promise가 끝날 때까지만 그 메뉴 항목 자체에
// 로딩 표시(스피너 등)를 보여주다가, 끝나면 실제(딱 한 번의) navigate만 실행한다 -
// 주소창에는 항상 최종 목적지만 나타난다.
export function useResolvedNavLinks() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  async function goToPersonalSearch() {
    if (!isAuthenticated) {
      navigate(DEFAULT_PLAYER_LINK);
      return;
    }
    const players = await fetchMyTeamPlayers();
    // resolvable === false인 선수는 Henrik이 실제 계정 존재를 확인해준 적 없는
    // "유령" 계정이다(services/my_team_players.py 참고) - 조회 가능한 선수 중
    // ACS 최고를 고른다. 필드 자체가 없으면(mock 등 구버전 응답) 조회 가능하다고
    // 간주해 하위 호환을 지킨다.
    const resolvable = (players || []).filter((p) => p.resolvable !== false);
    const top = resolvable[0];
    navigate(top ? ROUTES.player(top.name, top.tag) : DEFAULT_PLAYER_LINK);
  }

  async function goToTeamSearch() {
    if (!isAuthenticated) {
      navigate(DEFAULT_TEAM_LINK);
      return;
    }
    const opponent = await fetchRecentOpponent();
    navigate(opponent ? ROUTES.team(opponent.teamName, opponent.teamTag) : DEFAULT_TEAM_LINK);
  }

  async function goToPredict() {
    if (!isAuthenticated) {
      navigate(DEFAULT_PREDICT_LINK);
      return;
    }
    // "상대팀 전적 검색"과 완전히 같은 recent-opponent 조회.
    const opponent = await fetchRecentOpponent();
    navigate(opponent ? ROUTES.predict(opponent.teamName, opponent.teamTag) : DEFAULT_PREDICT_LINK);
  }

  return { goToPersonalSearch, goToTeamSearch, goToPredict };
}
