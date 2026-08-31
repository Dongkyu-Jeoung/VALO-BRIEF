// 비밀번호 정책: 8자 이상 + 영문/숫자/특수문자(!@#$%^&*) 조합.
// 정책이 바뀌면 이 파일만 수정하면 됩니다.
export const PASSWORD_REGEX = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$/;

export function validatePassword(password) {
  return PASSWORD_REGEX.test(password);
}
