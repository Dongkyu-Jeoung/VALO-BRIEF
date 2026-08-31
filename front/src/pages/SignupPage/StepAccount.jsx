import { useState } from 'react';
import { validatePassword } from '../../utils/passwordPolicy';
import { checkIdAvailable } from '../../api/auth';

export default function StepAccount({ form, onChange, onNext }) {
  const [errors, setErrors] = useState({});
  const [checkingId, setCheckingId] = useState(false);

  // 정규식 정의
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

  // 다음 단계 이동 핸들러
  const handleNext = async () => {
    let newErrors = {};

    // 1. 이메일 형식 검사
    if (!form.email.trim()) {
      newErrors.email = '이메일을 입력해 주세요.';
    } else if (!emailRegex.test(form.email)) {
      newErrors.email = '올바른 이메일 형식이 아닙니다.';
    }

    // 2. 아이디 입력 검사
    if (!form.id.trim()) {
      newErrors.id = '아이디를 입력해 주세요.';
    }

    // 3. 비밀번호 제약 조건 검사
    if (!form.password) {
      newErrors.password = '비밀번호를 입력해 주세요.';
    } else if (!validatePassword(form.password)) {
      newErrors.password = '8자 이상, 영문·숫자·특수문자를 조합해 주세요.';
    }

    // 4. 비밀번호 확인 일치 검사
    if (!form.confirmPassword) {
      newErrors.confirmPassword = '비밀번호 확인을 입력해 주세요.';
    } else if (form.password !== form.confirmPassword) {
      newErrors.confirmPassword = '비밀번호가 일치하지 않습니다.';
    }

    // 5. 약관 동의 검사
    if (!form.agree) {
      newErrors.agree = '이용약관에 동의해 주세요.';
    }

    // 아이디 형식이 유효할 때만 서버(mock) 중복 확인을 시도
    if (!newErrors.id) {
      setCheckingId(true);
      try {
        const res = await checkIdAvailable(form.id.trim());
        if (!res.available) {
          newErrors.id = '이미 사용 중인 아이디입니다.';
        }
      } catch {
        newErrors.id = '아이디 확인 중 오류가 발생했습니다.';
      } finally {
        setCheckingId(false);
      }
    }

    setErrors(newErrors);

    // 에러가 없을 때만 이동
    if (Object.keys(newErrors).length === 0) {
      onNext();
    }
  };

  return (
    <div className="auth-col">
      <div className="signup-progress-wrap">
        <div className="signup-progress">
          <div className="signup-progress-bar active" />
          <div className="signup-progress-bar" />
        </div>
        <div className="signup-step-label">STEP 1 / 2</div>
      </div>

      <div className="auth-title display">SIGN UP</div>

      {/* 이메일 */}
      <div className="field-block">
        <div className={`field ${errors.email ? 'is-invalid' : ''}`}>
          <input
            value={form.email}
            onChange={(e) => {
              onChange('email', e.target.value);
              if (errors.email) setErrors((prev) => ({ ...prev, email: '' }));
            }}
            placeholder="e - mail"
          />
        </div>
        {errors.email && <span className="field-error-msg">{errors.email}</span>}
      </div>

      {/* 아이디 */}
      <div className="field-block">
        <div className={`field ${errors.id ? 'is-invalid' : ''}`}>
          <input
            value={form.id}
            onChange={(e) => {
              onChange('id', e.target.value);
              if (errors.id) setErrors((prev) => ({ ...prev, id: '' }));
            }}
            placeholder="id"
          />
        </div>
        {checkingId && <span className="field-error-msg">아이디 중복 확인 중...</span>}
        {!checkingId && errors.id && <span className="field-error-msg">{errors.id}</span>}
      </div>

      {/* 비밀번호 */}
      <div className="field-block">
        <div className={`field ${errors.password ? 'is-invalid' : ''}`}>
          <input
            type="password"
            value={form.password}
            onChange={(e) => {
              onChange('password', e.target.value);
              if (errors.password) setErrors((prev) => ({ ...prev, password: '' }));
            }}
            placeholder="password ( 8자 이상, 영문 · 숫자 · 특수문자 )"
          />
        </div>
        {errors.password && <span className="field-error-msg">{errors.password}</span>}
      </div>

      {/* 비밀번호 확인 */}
      <div className="field-block">
        <div className={`field ${errors.confirmPassword ? 'is-invalid' : ''}`}>
          <input
            type="password"
            value={form.confirmPassword}
            onChange={(e) => {
              onChange('confirmPassword', e.target.value);
              if (errors.confirmPassword) setErrors((prev) => ({ ...prev, confirmPassword: '' }));
            }}
            placeholder="confirm password"
          />
        </div>
        {errors.confirmPassword && (
          <span className="field-error-msg">{errors.confirmPassword}</span>
        )}
      </div>

      {/* 약관 동의 */}
      <div className="field-block" style={{ marginBottom: '24px' }}>
        <div className="checkbox-row" style={{ marginBottom: '4px' }}>
          <input
            type="checkbox"
            checked={form.agree}
            onChange={(e) => {
              onChange('agree', e.target.checked);
              if (errors.agree) setErrors((prev) => ({ ...prev, agree: '' }));
            }}
          />
          <span>[필수] 이용약관 및 개인정보 수집·이용에 동의합니다.</span>
        </div>
        {errors.agree && <span className="field-error-msg">{errors.agree}</span>}
      </div>

      <button className="btn-auth-pill" onClick={handleNext} type="button" disabled={checkingId}>
        {checkingId ? '확인 중...' : 'NEXT >'}
      </button>
    </div>
  );
}