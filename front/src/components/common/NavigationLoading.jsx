import ProgressLoading from './ProgressLoading';

const CONTENT = {
  '/players': {
    variant: 'player',
    eyebrow: 'PLAYER PROFILE',
    title: '플레이어의 전적을 불러오는 중',
    description: '전적을 조회할 플레이어를 확인하고 있어요.',
    phase: '플레이어 확인 중',
  },
  '/teams': {
    variant: 'team',
    eyebrow: 'TEAM HISTORY',
    title: '상대 팀의 전적을 불러오는 중',
    description: '전적을 조회할 상대 팀을 확인하고 있어요.',
    phase: '상대 팀 확인 중',
  },
  '/predict': {
    variant: 'match',
    eyebrow: 'MATCH PREDICTION',
    title: '다음 승부를 준비하는 중',
    description: '승부를 예측할 상대 팀을 확인하고 있어요.',
    phase: '상대 팀 확인 중',
  },
};

export default function NavigationLoading({ destination }) {
  return (
    <div className="navigation-loading-overlay">
      <ProgressLoading {...(CONTENT[destination] || CONTENT['/teams'])} />
    </div>
  );
}
