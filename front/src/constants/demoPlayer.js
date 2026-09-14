// 로그인 전/기본 진입용 데모 선수 (실제로 존재하지 않는 Riot 계정이라 백엔드 조회가
// 항상 404). 헤더/메뉴바의 "개인 검색" 기본값(useResolvedNavLinks 참고)과 일부 mock
// 문서의 예시로 쓴다.
//
// front/src/api/players.js::fetchPlayerProfile이 이 값과 일치하는 요청은 아예 네트워크를
// 타지 않고 바로 mock을 반환한다(2026-09-14) - 안 그러면 비로그인 사용자가 "개인 검색"을
// 누를 때마다, 또는 "최근 상대팀"을 못 정한 로그인 사용자가 어쩌다 이 기본값을 클릭할
// 때마다 백엔드에 뻔한 404 요청이 나갔다(constants/demoTeam.js의 DEMO_TEAM과 동일 문제).
export const DEMO_PLAYER_NAME = 'example';
export const DEMO_PLAYER_TAG = '0000';
