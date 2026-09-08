import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMe, updateMe, deleteMe } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';
import EmptyImageBox from '../../components/common/EmptyImageBox';
import LoadingText from '../../components/common/LoadingText';
import '@/styles/pages/myPage.css';

/**
 * 마이페이지 - 로그인한 팀 계정 조회/수정/탈퇴 (routers/auth.py: GET·PATCH·DELETE /api/auth/me).
 * 헤더 햄버거 메뉴(UtilHeader.jsx)의 '마이페이지' 링크로 진입.
 */
export default function MyPage() {
  const navigate = useNavigate();
  const { logout } = useAuth();

  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState('');
  const [emailMsg, setEmailMsg] = useState('');
  const [savingEmail, setSavingEmail] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [passwordMsg, setPasswordMsg] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);

  const [deletePassword, setDeletePassword] = useState('');
  const [deleteMsg, setDeleteMsg] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    getMe().then((res) => {
      if (!active) return;
      setTeam(res);
      setEmail(res.email);
      setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const emailDirty = team && email.trim() !== '' && email.trim() !== team.email;
  const passwordFilled = currentPassword && newPassword && confirmNewPassword;

  async function handleEmailSave(e) {
    e.preventDefault();
    setEmailMsg('');
    if (!email.trim()) {
      setEmailMsg('이메일을 입력해 주세요.');
      return;
    }
    setSavingEmail(true);
    try {
      const updated = await updateMe({ email: email.trim() });
      setTeam(updated);
      setEmailMsg('이메일이 변경되었습니다.');
    } catch {
      setEmailMsg('이메일 변경에 실패했습니다. 이미 사용 중인 이메일일 수 있습니다.');
    } finally {
      setSavingEmail(false);
    }
  }

  async function handlePasswordSave(e) {
    e.preventDefault();
    setPasswordMsg('');
    if (!currentPassword || !newPassword) {
      setPasswordMsg('현재 비밀번호와 새 비밀번호를 입력해 주세요.');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordMsg('새 비밀번호가 일치하지 않습니다.');
      return;
    }
    setSavingPassword(true);
    try {
      await updateMe({ currentPassword, newPassword });
      setPasswordMsg('비밀번호가 변경되었습니다.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
    } catch {
      setPasswordMsg('비밀번호 변경에 실패했습니다. 현재 비밀번호를 확인해 주세요.');
    } finally {
      setSavingPassword(false);
    }
  }

  async function handleDelete(e) {
    e.preventDefault();
    setDeleteMsg('');
    if (!deletePassword) {
      setDeleteMsg('비밀번호를 입력해 주세요.');
      return;
    }
    setDeleting(true);
    try {
      await deleteMe(deletePassword);
      logout();
      navigate('/');
    } catch {
      setDeleteMsg('탈퇴에 실패했습니다. 비밀번호를 확인해 주세요.');
      setDeleting(false);
    }
  }

  if (loading || !team) return <LoadingText full />;

    return (
    <div className="page-container my-page">
      <div className="my-page-inner">
        <div className="profile-card">
          <EmptyImageBox src={team.teamImage} label={`TEAM\nIMAGE`} className="avatar-frame" />
          <div>
            <div className="profile-name display">
              {team.teamName} <span className="tagline">#{team.teamTag}</span>
            </div>
            <div className="profile-meta">
              <span>아이디 : <b>{team.loginId}</b></span>
              <span>가입일 : <b>{(team.createdAt || '').slice(0, 10) || '-'}</b></span>
            </div>
          </div>
        </div>

        <div className="mh-box">
          <div className="mh-box-info">
            <h5>이메일</h5>
            <p className="mh-box-desc">계정에 연결된 이메일<br />주소를 변경합니다.</p>
          </div>
          <form onSubmit={handleEmailSave} className="my-page-form">
            <div className="field-block">
              <label className="field-label" htmlFor="email">EMAIL ADDRESS</label>
              <div className="field">
                <input id="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e-mail" />
              </div>
              {emailMsg && <span className="field-error-msg">{emailMsg}</span>}
            </div>
            <div className="my-page-form-actions">
              <button type="submit" className="btn btn-solid" disabled={savingEmail || !emailDirty}>
                {savingEmail ? '저장 중...' : '저장'}
              </button>
            </div>
          </form>
        </div>

        <div className="mh-box">
          <div className="mh-box-info">
            <h5>비밀번호 변경</h5>
            <p className="mh-box-desc">계정 보안을 위해 주기적으로<br />비밀번호를 변경해 주세요.</p>
          </div>
          <form onSubmit={handlePasswordSave} className="my-page-form">
            <div className="field-block">
              <label className="field-label" htmlFor="currentPw">CURRENT PASSWORD</label>
              <div className="field">
                <input
                  id="currentPw"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </div>
            </div>
            <div className="field-block">
              <label className="field-label" htmlFor="newPw">NEW PASSWORD</label>
              <div className="field">
                <input
                  id="newPw"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
            </div>
            <div className="field-block">
              <label className="field-label" htmlFor="confirmPw">CONFIRM NEW PASSWORD</label>
              <div className="field">
                <input
                  id="confirmPw"
                  type="password"
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                />
              </div>
              {passwordMsg && <span className="field-error-msg">{passwordMsg}</span>}
            </div>
            <div className="my-page-form-actions">
              <button type="submit" className="btn btn-solid" disabled={savingPassword || !passwordFilled}>
                {savingPassword ? '저장 중...' : '저장'}
              </button>
            </div>
          </form>
        </div>

        <div className="mh-box my-page-danger">
          <div className="mh-box-info">
            <h5>회원 탈퇴</h5>
            <p className="mh-box-desc">탈퇴하면 계정 정보가 즉시 삭제되며<br />되돌릴 수 없습니다.</p>
          </div>
          <form onSubmit={handleDelete} className="my-page-form">
            <div className="field-block">
              <label className="field-label" htmlFor="deletePw">PASSWORD</label>
              <div className="field">
                <input
                  id="deletePw"
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                />
              </div>
              {deleteMsg && <span className="field-error-msg">{deleteMsg}</span>}
            </div>
            <div className="my-page-form-actions">
              <button
                type="submit"
                className="btn btn-solid my-page-delete-btn"
                disabled={deleting || !deletePassword}
              >
                {deleting ? '처리 중...' : '회원 탈퇴'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}