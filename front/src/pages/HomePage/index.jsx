import { useState } from 'react';
import Hero from './Hero';
import FeatureRow from './FeatureRow';
import QuickAnalysisModal from '../QuickAnalysisModal';
import { ROUTES } from '../../constants/routes';

// 데모용 팀(목업 데이터의 teamProfileMock과 동일한 팀)으로 연결합니다.
const DEMO_TEAM_NAME = 'team-ascend';
const DEMO_TEAM_TAG = 'ASC';

export default function HomePage() {
  const [quickAnalysisTeamTag, setQuickAnalysisTeamTag] = useState(null);

  const openQuickAnalysis = () => setQuickAnalysisTeamTag(DEMO_TEAM_TAG);
  const closeQuickAnalysis = () => setQuickAnalysisTeamTag(null);

  const PILLS = [
    { label: '정확한 승률 예측', to: ROUTES.predict(DEMO_TEAM_NAME, DEMO_TEAM_TAG) },
    { label: 'AI 전술 분석', onClick: openQuickAnalysis },
    { label: '맞춤 전략 제안', to: `${ROUTES.myTeam}?tab=${encodeURIComponent('AI 리포트')}` },
  ];

  const FEATURES = [
    {
      title: '3초 상대분석 리포트',
      description: '팀 이름 검색 한 번으로 상대의 최근 전적과 티어, 개인 순위를 즉시 요약해드립니다.',
      linkText: '리포트 보러가기',
      onClick: openQuickAnalysis,
    },
    {
      title: '상대팀 VS 우리팀 분석',
      description: '저장된 우리 팀 데이터를 기반으로 승률을 예측하고 세부 통계를 비교합니다.',
      linkText: '비교 분석 보러가기',
      to: ROUTES.predict(DEMO_TEAM_NAME, DEMO_TEAM_TAG),
    },
    {
      title: '우리팀 맞춤 전략 제안',
      description: 'AI가 상대의 강점과 약점을 분석해 우리 팀에 맞는 전술을 리포트로 제공합니다.',
      linkText: '전략 제안 보러가기',
      to: `${ROUTES.myTeam}?tab=${encodeURIComponent('AI 리포트')}`,
    },
  ];

  return (
    <>
      <Hero pills={PILLS} />
      <section className="feature-strip">
        <div className="feature-rows">
          {FEATURES.map((f, i) => (
            <FeatureRow key={f.title} index={i + 1} {...f} />
          ))}
        </div>
      </section>
      {quickAnalysisTeamTag ? (
        <QuickAnalysisModal teamTag={quickAnalysisTeamTag} onClose={closeQuickAnalysis} />
      ) : null}
    </>
  );
}
