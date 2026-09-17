import ProgressLoading from '../common/ProgressLoading';

export default function PredictionLoading({ opponentName, opponentResolved = false }) {
  return (
    <ProgressLoading
      eyebrow="MATCH PREDICTION"
      title="다음 승부를 준비하는 중"
      subject={opponentName ? `상대 팀 · ${opponentName}` : null}
      description={opponentResolved
        ? '최근 Premier 경기 기록을 바탕으로 양 팀의 승률을 준비하고 있어요.'
        : '승부를 예측할 상대 팀을 확인하고 있어요.'}
      phase={opponentResolved ? '예측 응답 대기 중' : '상대 팀 확인 중'}
    />
  );
}
