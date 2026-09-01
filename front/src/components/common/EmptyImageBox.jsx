import { getAsset } from '@/assets';

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