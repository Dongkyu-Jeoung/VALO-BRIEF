import { useState } from 'react';
import { verifyRiotId } from '../../api/auth';
import riotLogo from '../../assets/images/logo/logo.png';

// status: 'idle' | 'verifying' | 'verified' | 'failed'
export default function StepTeamInfo({ form, onChange, onSubmit }) {
  const [status, setStatus] = useState('idle');
  const [errors, setErrors] = useState({});

  // 범용 라이엇 계정 로그인 URL (만료 파라미터 제거) — 시각적 흐름을 위해 그대로 열되,
  // 인증 상태는 팝업 자체가 아니라 verifyRiotId() 응답으로만 결정합니다.
  const RIOT_AUTH_URL = 'https://auth.riotgames.com/authorize?client_id=play-valorant-web-prod&response_type=token&redirect_uri=https://playvalorant.com/opt_in&scope=openid+account';

  // Riot ID 검증: idle → verifying → verified/failed (mock API 응답이 상태를 결정)
  async function handleVerify() {
    if (!form.teamName?.trim() || !form.teamTag?.trim()) {
      setErrors((prev) => ({ ...prev, riot: '팀 이름과 태그를 먼저 입력해 주세요.' }));
      return;
    }

    setStatus('verifying');
    setErrors((prev) => ({ ...prev, riot: '' }));

    try {
      const res = await verifyRiotId({ teamName: form.teamName, teamTag: form.teamTag });

      if (res?.verified) {
        setStatus('verified');

        // 화면 중앙 팝업창은 시각적 연출용으로만 유지 (인증 완료 여부에는 영향 없음)
        const width = 480;
        const height = 640;
        const left = window.screenX + (window.innerWidth - width) / 2;
        const top = window.screenY + (window.innerHeight - height) / 2;
        window.open(
          RIOT_AUTH_URL,
          'RiotAuthPopup',
          `width=${width},height=${height},top=${top},left=${left},resizable=yes,scrollbars=yes`
        );
      } else {
        setStatus('failed');
        setErrors((prev) => ({ ...prev, riot: 'Riot 계정을 찾을 수 없거나 인증에 실패했습니다.' }));
      }
    } catch (err) {
      setStatus('failed');
      setErrors((prev) => ({ ...prev, riot: '인증 중 오류가 발생했습니다.' }));
    }
  }

  // 최종 제출
  const handleFinalSubmit = () => {
    let newErrors = {};

    if (!form.teamName?.trim()) newErrors.teamName = '팀 이름을 입력해 주세요.';
    if (!form.teamTag?.trim()) newErrors.teamTag = '태그를 입력해 주세요.';
    if (status !== 'verified') newErrors.riot = 'Riot ID 인증을 완료해 주세요.';

    setErrors(newErrors);

    if (Object.keys(newErrors).length === 0) {
      onSubmit();
    }
  };

  return (
    <div className="auth-col">
      <div className="signup-progress-wrap">
        <div className="signup-progress">
          <div className="signup-progress-bar active" />
          <div className="signup-progress-bar active" />
        </div>
        <div className="signup-step-label right">STEP 2 / 2</div>
      </div>

      <div className="auth-title display">팀 정보 등록하기</div>

      {/* 팀 이름 */}
      <div className="field-block">
        <div className={`field ${errors.teamName ? 'is-invalid' : ''}`}>
          <input
            value={form.teamName || ''}
            onChange={(e) => {
              onChange('teamName', e.target.value);
              if (errors.teamName) setErrors((prev) => ({ ...prev, teamName: '' }));
            }}
            placeholder="team - name"
          />
        </div>
        {errors.teamName && <span className="field-error-msg">{errors.teamName}</span>}
      </div>

      {/* 태그 */}
      <div className="field-block">
        <div className={`field ${errors.teamTag ? 'is-invalid' : ''}`}>
          <input
            value={form.teamTag || ''}
            onChange={(e) => {
              onChange('teamTag', e.target.value);
              if (errors.teamTag) setErrors((prev) => ({ ...prev, teamTag: '' }));
            }}
            placeholder="# tag"
          />
        </div>
        {errors.teamTag && <span className="field-error-msg">{errors.teamTag}</span>}
      </div>

      {/* Riot ID 인증 영역 */}
      <div className="field-block">
        <div className="riot-verify-box">
          <span className={`riot-status-text ${status === 'verified' ? 'is-verified' : ''}`}>
            {status === 'verified' && 'RIOT ID 연동 완료'}
            {status === 'verifying' && 'RIOT ID 인증 요청 중...'}
            {status === 'failed' && 'RIOT ID 인증 실패 · 다시 시도해 주세요'}
            {status === 'idle' && 'RIOT ID 인증 · 최초 1회 필요'}
          </span>
          <button
            className={`btn-riot-red ${status === 'verified' ? 'is-verified-btn' : ''}`}
            type="button"
            onClick={handleVerify}
            disabled={status === 'verifying' || status === 'verified'}
          >
            <img src={riotLogo} alt="Riot Logo" className="riot-logo-img" />
            <span>
              {status === 'verifying' && '인증 요청 중...'}
              {status === 'verified' && '연동 완료'}
              {(status === 'idle' || status === 'failed') && 'Riot ID로 로그인'}
            </span>
          </button>
        </div>
        {errors.riot && <span className="field-error-msg">{errors.riot}</span>}
      </div>

      {/* 하단 안내 문구 */}
      <p className="auth-disclaimer">
        ※ 서비스 이용 및 전공·매치 데이터 분석을 위해 라이엇 계정 연동 정보가 수집될 수 있습니다.
      </p>

      {/* 제출 버튼 */}
      <button className="btn-auth-pill" type="button" onClick={handleFinalSubmit}>
        SIGNUP
      </button>
    </div>
  );
}