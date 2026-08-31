import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import StepAccount from './StepAccount';
import StepTeamInfo from './StepTeamInfo';
import { signup } from '../../api/auth';

const INITIAL_FORM = {
  email: '',
  id: '',
  password: '',
  confirmPassword: '',
  agree: false,
  teamName: '',
  teamTag: '',
};

export default function SignupPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(INITIAL_FORM);

  const handleChange = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  async function handleSubmit() {
    try {
      await signup(form);
      alert('회원가입이 완료되었습니다!');
      navigate('/login');
    } catch (err) {
      alert('회원가입 처리 중 오류가 발생했습니다.');
    }
  }

  return step === 1 ? (
    <StepAccount
      form={form}
      onChange={handleChange}
      onNext={() => setStep(2)}
    />
  ) : (
    <StepTeamInfo
      form={form}
      onChange={handleChange}
      onPrev={() => setStep(1)}
      onSubmit={handleSubmit}
    />
  );
}