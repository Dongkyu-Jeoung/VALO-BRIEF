import { useState, useEffect } from 'react';
import { getAsset } from '@/assets';

export default function EmptyImageBox({
  folder,
  assetKey,
  src,
  alt = '',
  label,
  className = '',
  style
}) {
  const resolvedSrc = src ?? (folder && assetKey ? getAsset(folder, assetKey) : null);
  const [hasError, setHasError] = useState(false);

  // src나 자산 키가 바뀌면 에러 상태를 초기화
  useEffect(() => {
    setHasError(false);
  }, [resolvedSrc]);

  if (!resolvedSrc || hasError) {
    return (
      <div
        className={`empty-image-box ${className}`.trim()}
        style={style}
      >
        {label}
      </div>
    );
  }

  return (
    <img
      src={resolvedSrc}
      alt={alt}
      className={className}
      style={style}
      onError={() => setHasError(true)}
    />
  );
}