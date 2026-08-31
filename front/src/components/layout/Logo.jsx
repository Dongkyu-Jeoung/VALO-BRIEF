import { getAsset } from '@/assets';

/**
 * src/assets/images/logo/full.(png|svg) 에 로고 이미지를 넣으면 그 옆에
 * "VALO - BRIEF" 텍스트가 함께 표시됩니다. 크기는 size prop("md"|"sm")에 따라
 * styles/layout/header.css 의 .brand / .brand.sm 규칙이 결정합니다.
 */
export default function Logo({ size = 'md' }) {
  const logoImage = getAsset('logo', 'full');

  return (
    <div className={`brand ${size === 'sm' ? 'sm' : ''}`.trim()}>
      {logoImage ? <img src={logoImage} alt="" /> : null}
      <div className="brand-text">VALO - BRIEF</div>
    </div>
  );
}
