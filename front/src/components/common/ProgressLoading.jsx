import { useEffect, useState } from 'react';
import { FiUser, FiUsers } from 'react-icons/fi';
import '../../styles/components/predictionLoading.css';

export default function ProgressLoading({ title, eyebrow, subject, description, phase, variant = 'match' }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const message = elapsed >= 30
    ? '경기 데이터를 불러오는 데 시간이 걸리고 있어요. 잠시만 기다려 주세요.'
    : description;

  return (
    <section className="prediction-loading" aria-busy="true" aria-label={title}>
      <div className="prediction-loading__card">
        <div className="prediction-loading__eyebrow">{eyebrow}</div>
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
        <h2>{title}</h2>
        {subject && <p className="prediction-loading__opponent">{subject}</p>}
        <p className="prediction-loading__message" role="status">{message}</p>
        {/* 서버의 진행률 정보가 없으므로 완료 비율을 표시하지 않는 진행 막대. */}
        <div className="prediction-loading__track" role="progressbar" aria-label={phase}>
          <span className="prediction-loading__beam" />
        </div>
        <div className="prediction-loading__footer">
          <span className="prediction-loading__phase"><i aria-hidden="true" />{phase}</span>
          <span className="prediction-loading__elapsed" aria-hidden="true">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</span>
        </div>
      </div>
    </section>
  );
}
