import DuelCompareBar from '../common/DuelCompareBar';

/**
 * "상대 팀 검색 → 승부예측 → 분석" 탭 ③번 전용 블록. 기존 EngagementInfoBlock(과거 N경기
 * 트레이드/스킬/듀얼리스트 실측 통계, 우리팀 분석 화면과 공유)과 달리 이건 "AI 모델이
 * 이번 매치업을 예측한 값"을 보여준다 - 그래서 컴포넌트를 따로 뺐다(우리팀 분석 화면은
 * 그대로 EngagementInfoBlock을 씀, AnalysisSection.jsx 참고).
 *
 * data가 null/undefined면 "모델 학습 전" 상태로 렌더링한다 - 아직 트레이드 성공률/
 * 듀얼리스트 매치업 예측 모델이 없으므로(server/승부예측_성능_분석.md 7번 참고) 실제
 * 백엔드 연동 초기에는 이 상태가 정상이다.
 *
 * data shape (server/승부예측_성능_분석.md 7번의 API 계약과 동일하게 맞출 것):
 * {
 *   trade: { ourWinRate: number, theirWinRate: number },       // 1대1 트레이드 성공률 예측(%)
 *   duelistMatchup: { ourScore: number, theirScore: number, favor: 'us'|'them'|'even' },
 *   modelVersion?: string,
 * }
 */
export default function EngagementPredictionBlock({
  data,
  title = '③ 교전 매치업 예측',
  ourLabel = '우리팀',
  theirLabel = '상대팀',
}) {
  if (!data) {
    return (
      <div className="analysis-row">
        <div className="analysis-row-head">
          <h5>{title} <span className="tag">AI</span></h5>
        </div>
        <div className="empty-text">
          아직 학습된 예측 모델이 없어 이 매치업의 교전 예측을 준비 중입니다.
        </div>
      </div>
    );
  }

  const trade = data.trade ?? { ourWinRate: 50, theirWinRate: 50 };
  const duel = data.duelistMatchup ?? { ourScore: 50, theirScore: 50, favor: 'even' };

  const favorText =
    duel.favor === 'us' ? `${ourLabel} 우세` : duel.favor === 'them' ? `${theirLabel} 우세` : '팽팽함';
  const favorClass = duel.favor === 'us' ? 'text-win' : duel.favor === 'them' ? 'text-lose' : '';

  return (
    <div className="analysis-row">
      <div className="analysis-row-head">
        <h5>{title} <span className="tag">AI</span></h5>
      </div>

      <div className="duel-compare-block">
        <div className="duel-compare-title">트레이드 성공률 예측 (1대1 교전 기준)</div>
        <DuelCompareBar
          leftLabel={ourLabel}
          leftPct={trade.ourWinRate}
          rightLabel={theirLabel}
          rightPct={trade.theirWinRate}
        />
      </div>

      <div className="duel-compare-block">
        <div className="duel-compare-title">듀얼리스트 매치업 유불리 예측</div>
        <DuelCompareBar
          leftLabel={ourLabel}
          leftPct={duel.ourScore}
          rightLabel={theirLabel}
          rightPct={duel.theirScore}
        />
        <div className={`matchup-favor-text ${favorClass}`.trim()}>
          예측 결과: <span>{favorText}</span>
        </div>
      </div>

      {data.modelVersion ? (
        <div className="empty-text model-version-note">모델 버전: {data.modelVersion}</div>
      ) : null}
    </div>
  );
}
