import { useState } from 'react';
import Hero from './Hero';
import FeatureRow from './FeatureRow';
import QuickAnalysisModal from '../QuickAnalysisModal';
import { quickAnalysisMock } from '../../mocks/team.mock';
import { ROUTES } from '../../constants/routes';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../../constants/demoTeam';

export default function HomePage() {
  const [quickAnalysisTeam, setQuickAnalysisTeam] = useState(null);

  const openQuickAnalysis = () => setQuickAnalysisTeam({ name: DEMO_TEAM_NAME, tag: DEMO_TEAM_TAG });
  const closeQuickAnalysis = () => setQuickAnalysisTeam(null);

  const PILLS = [
    { label: '정확한 승률 예측' },
    { label: 'AI 전술 분석' },
    { label: '맞춤 전략 제안' },
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
      {quickAnalysisTeam ? (
        <QuickAnalysisModal
          teamName={quickAnalysisTeam.name}
          teamTag={quickAnalysisTeam.tag}
          // team-ascend/ASC는 실제로 존재하지 않는 데모용 팀명이라, 실제 백엔드가 붙어있으면
          // 열 때마다 Henrik 조회 2건이 404로 끝난 뒤에야 mock으로 폴백해서 느려 보이고
          // 레이트리밋 예산도 낭비했다 - mock을 바로 넘겨 첫 fetch를 건너뛴다.
          initialData={quickAnalysisMock}
          onClose={closeQuickAnalysis}
        />
      ) : null}
    </>
  );
}
