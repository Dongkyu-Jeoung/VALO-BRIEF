import { useState, useEffect } from 'react';
import { getAsset } from '@/assets';
import { API_BASE_URL } from '../../api/config';

export default function EmptyImageBox({
  folder,
  assetKey,
  src,
  alt = '',
  label,
  className = '',
  style
}) {
  // 백엔드가 자체 프록시(예: /api/team-icons/...)를 상대경로로 내려줄 때가 있다
  // (services/team_profile.py::resolve_team_icon_url) - API_BASE_URL을 붙여야 실제
  // 백엔드 origin으로 요청이 나간다. 다른 소스(Henrik/valorant-api.com 등)는 이미
  // 절대경로라 그대로 둔다.
  const rawSrc = src ?? (folder && assetKey ? getAsset(folder, assetKey) : null);
  const resolvedSrc = rawSrc && rawSrc.startsWith('/api/') ? `${API_BASE_URL}${rawSrc}` : rawSrc;
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