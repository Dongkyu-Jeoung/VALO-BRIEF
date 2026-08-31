import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { login } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import '@/styles/pages/login.css';

export default function LoginPage() {
  const navigate = useNavigate();
  const { applySession } = useAuth();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [idError, setIdError] = useState('');
  const [passwordError, setPasswordError] = useState('');

  useEffect(() => {
    const savedId = localStorage.getItem('savedUserId');
    if (savedId) {
      setId(savedId);
      setRememberMe(true);
    }
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setIdError('');
    setPasswordError('');

    let hasError = false;

    if (!id.trim()) {
      setIdError('아이디를 입력해 주세요.');
      hasError = true;
    }

    if (!password.trim()) {
      setPasswordError('비밀번호를 입력해 주세요.');
      hasError = true;
    }

    if (hasError) return;

    try {
      const result = await login({ id, password });
      applySession(result);

      if (rememberMe) {
        localStorage.setItem('savedUserId', id.trim());
      } else {
        localStorage.removeItem('savedUserId');
      }

      navigate('/my-team');
    } catch (err) {
      setPasswordError('로그인에 실패했습니다. 아이디/비밀번호를 확인해주세요.');
    }
  }

  return (
    <div className="auth-col">
      <div className="auth-title-lg display">LOG IN</div>

      <form onSubmit={handleSubmit} noValidate className="login-form">
        {/* ID 입력 블록 */}
        <div className="field-block">
          <div className={`field ${idError ? 'is-invalid' : ''}`}>
            <input
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                if (idError) setIdError('');
              }}
              placeholder="id"
            />
          </div>
          {idError && <span className="field-error-msg">{idError}</span>}
        </div>

        {/* PASSWORD 입력 블록 */}
        <div className="field-block">
          <div className={`field field-icon-wrap ${passwordError ? 'is-invalid' : ''}`}>
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (passwordError) setPasswordError('');
              }}
              placeholder="password"
            />
            <button
              type="button"
              className="field-icon-btn"
              onClick={() => setShowPassword((v) => !v)}
              aria-label="비밀번호 표시 전환"
            >
              {showPassword ? <FaEyeSlash className="eye-icon" /> : <FaEye className="eye-icon" />}
            </button>
          </div>
          {passwordError && <span className="field-error-msg">{passwordError}</span>}
        </div>

        {/* 체크박스 영역 */}
        <div className="checkbox-row">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            <span>아이디 저장하기</span>
          </label>
        </div>

        <button className="btn-auth-pill" type="submit">login</button>
      </form>

      <div className="auth-foot-link">
        계정이 없으신가요? · <Link to="/signup"><span>SIGNUP</span></Link>
      </div>
    </div>
  );
}