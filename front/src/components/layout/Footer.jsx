import { FaYoutube, FaInstagram, FaFacebookF, FaXTwitter } from 'react-icons/fa6';

const SNS = [
  { label: 'YouTube', Icon: FaYoutube },
  { label: 'Instagram', Icon: FaInstagram },
  { label: 'Facebook', Icon: FaFacebookF },
  { label: 'X', Icon: FaXTwitter },
];

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-links">
        {SNS.map(({ label, Icon }) => (
          <div className="sns-dot" key={label} title={label}>
            <Icon size={14} />
          </div>
        ))}
      </div>

      <hr className="footer-divider" />

      <div className="footer-legal">
        <span>이용약관</span>
        <span>|</span>
        <span>개인정보처리방침</span>
      </div>

      <p className="footer-disclaimer">
        VALO-BRIEF는 라이엇 게임즈의 보증을 받지 않으며,<br />
        라이엇 게임즈 또는 라이엇 게임즈 자산을 제작/관리하는 데 공식적으로 참여한 사람들의 견해나 의견을 반영하지 않습니다.<br />
        Riot Games 및 관련 모든 자산은 Riot Games, Inc.의 상표 또는 등록 상표입니다.
      </p>

      <p className="footer-copyright">Copyright © 2026 VALO-BRIEF. All rights reserved.</p>
    </footer>
  );
}