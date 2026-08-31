import { getAsset } from '@/assets';

/**
 * 이미지 자산 표시 공용 컴포넌트.
 *
 * - folder + assetKey 를 넘기면 src/assets/images/{folder}/{assetKey}.* 를 자동으로 찾아 렌더링합니다.
 *   (파일이 아직 없으면 자동으로 placeholder로 대체됩니다 → 이미지 준비 전/후 코드가 동일합니다)
 * - src를 직접 넘기면 그 값을 최우선으로 사용합니다.
 * - 둘 다 없으면 점선 placeholder 박스 + label 텍스트를 보여줍니다.
 */
export default function EmptyImageBox({ folder, assetKey, src, alt = '', label, className = '', style }) {
  const resolvedSrc = src ?? (folder && assetKey ? getAsset(folder, assetKey) : null);

  if (resolvedSrc) {
    return <img src={resolvedSrc} alt={alt} className={className} style={style} />;
  }
  return (
    <div className={`empty-image-box ${className}`.trim()} style={style}>
      {label}
    </div>
  );
}
