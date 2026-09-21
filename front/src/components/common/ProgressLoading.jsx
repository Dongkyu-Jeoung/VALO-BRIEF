import { useEffect, useState } from 'react';
import { FiUser, FiUsers } from 'react-icons/fi';
import '../../styles/components/predictionLoading.css';

const VARIANT_DEFAULTS = {
  player: {
    eyebrow: 'PLAYER PROFILE',
    title: '선수 전적을 불러오는 중',
    description: '최근 경기 기록과 통계를 가져오고 있어요.',
    phase: '전적 불러오는 중',
  },
  team: {
    eyebrow: 'TEAM PROFILE',
    title: '팀 전적을 불러오는 중',
    description: '팀의 최근 경기 기록과 통계를 가져오고 있어요.',
    phase: '팀 데이터 불러오는 중',
  },
  account: {
    eyebrow: 'MY PAGE',
    title: '내 계정을 불러오는 중',
    description: '팀 계정 정보를 가져오고 있어요.',
    phase: '계정 정보 불러오는 중',
  },
};

export default function ProgressLoading({ title, eyebrow, subject, description, phase, variant = 'match' }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const defaults = VARIANT_DEFAULTS[variant] ?? {};
  const resolvedTitle = title ?? defaults.title;
  const resolvedEyebrow = eyebrow ?? defaults.eyebrow;
  const resolvedDescription = description ?? defaults.description;
  const resolvedPhase = phase ?? defaults.phase;

  const message = elapsed >= 30
    ? '경기 데이터를 불러오는 데 시간이 걸리고 있어요. 잠시만 기다려 주세요.'
    : resolvedDescription;

  return (
    <section className="prediction-loading" aria-busy="true" aria-label={resolvedTitle}>
      <div className="prediction-loading__card">
        <div className="prediction-loading__eyebrow">{resolvedEyebrow}</div>
        <div className="prediction-loading__matchup" aria-hidden="true">
          {variant === 'match' ? <>
          <span className="prediction-loading__emblem prediction-loading__emblem--blue prediction-loading__emblem--label">우리팀</span>
          <span className="prediction-loading__vs">VS</span>
          <span className="prediction-loading__emblem prediction-loading__emblem--red prediction-loading__emblem--label">상대팀</span>
          </> : (
            <span className={`prediction-loading__emblem prediction-loading__emblem--${variant === 'player' ? 'blue' : 'red'}`}>
              {variant === 'player' ? <FiUser /> : <FiUsers />}
            </span>
          )}
        </div>
        <h2>{resolvedTitle}</h2>
        {subject && <p className="prediction-loading__opponent">{subject}</p>}
        <p className="prediction-loading__message" role="status">{message}</p>
        <div className="prediction-loading__track" role="progressbar" aria-label={resolvedPhase}>
          <span className="prediction-loading__beam" />
        </div>
        <div className="prediction-loading__footer">
          <span className="prediction-loading__phase"><i aria-hidden="true" />{resolvedPhase}</span>
          <span className="prediction-loading__elapsed" aria-hidden="true">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</span>
        </div>
      </div>
    </section>
  );
}