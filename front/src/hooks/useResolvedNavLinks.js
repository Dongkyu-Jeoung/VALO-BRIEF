import { useNavigate } from 'react-router-dom';
import { fetchPersonalSearchTarget } from '../api/myTeam';
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
    // 서버가 로스터 중 ACS 최고이면서 "지금도" Henrik에서 실제로 조회되는 선수를 골라
    // 내려준다(services/my_team_players.py::resolve_personal_search_target) - 예전엔
    // 프론트가 단순히 목록의 첫 번째(ACS 최고)만 골랐는데, 그 선수가 그 사이 Riot ID를
    // 바꿨으면 프로필이 텅 빈 채로 뜨는 문제가 있었다(2026-09-14, SPF#FF2 사례).
    const target = await fetchPersonalSearchTarget();
    navigate(target ? ROUTES.player(target.name, target.tag) : DEFAULT_PLAYER_LINK);
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
