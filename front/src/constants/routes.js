export const ROUTES = {
  home: '/',
  login: '/login',
  signup: '/signup',
  player: (riotId = ':riotId', tag = ':tag') => `/players/${riotId}/${tag}`,
  team: (teamName = ':teamName', teamTag = ':teamTag') => `/teams/${teamName}/${teamTag}`,
  predict: (teamName = ':teamName', teamTag = ':teamTag') => `/predict/${teamName}/${teamTag}`,
  myTeam: '/my-team',
};
