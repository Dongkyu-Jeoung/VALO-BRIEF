import { getAsset } from '@/assets';
import SearchBox from '../../components/search/SearchBox';
import FeatureLink from '../../components/common/FeatureLink';

export default function Hero({ pills = [] }) {
  const heroImage = getAsset('hero', 'home');

  return (
    <>
      <section className="hero" style={heroImage ? { backgroundImage: `url(${heroImage})` } : undefined}>
        <div className="hero-overlay" />

        <div className="hero-content">
          <h1 className="hero-headline display">
            데이터로<br /><span className="hi-accent">승리를 설계</span>하다
          </h1>
          <p className="hero-sub">
            상대 팀의 공개 데이터를 자동 분석하고,<br />우리 팀에 최적화된 전략을 제안합니다.
          </p>

          <div className="hero-center-group">
            <SearchBox variant="hero" />

            <div className="feature-pills">
              {pills.map((pill) => (
                <FeatureLink key={pill.label} to={pill.to} onClick={pill.onClick} className="feature-pill">
                  {pill.label}
                </FeatureLink>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="stats-bar">
        <div className="stats-bar-content">
          <div className="stat-item">
            <span className="stat-value">124,800+</span>
            <span className="stat-label">분석된 매치 데이터</span>
          </div>
          <div className="stat-divider" />
          <div className="stat-item">
            <span className="stat-value">98.2%</span>
            <span className="stat-label">전술 분석 만족도</span>
          </div>
          <div className="stat-divider" />
          <div className="stat-item">
            <span className="stat-value">3 초</span>
            <span className="stat-label">평균 리포트 생성 시간</span>
          </div>
        </div>
      </div>
    </>
  );
}