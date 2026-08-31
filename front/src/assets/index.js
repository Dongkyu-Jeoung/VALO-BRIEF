// ============================================================
// 이미지 자산 레지스트리
// ------------------------------------------------------------
// src/assets/images/{agents,weapons,maps,hitbox,teams,logo,rating,icons}
// 폴더에 파일을 넣기만 하면 자동으로 인식됩니다. (import 문 추가할 필요 없음)
//
// 사용법:
//   import { getAsset } from '@/assets';
//   const src = getAsset('agents', '제트');   // 없으면 null 반환 → EmptyImageBox가 placeholder로 표시
//
// 파일명 규칙 (확장자 제외한 이름이 key가 됩니다):
//   agents/제트.png, agents/jett.png 등 자유롭게. 컴포넌트에서 쓰는 key와 파일명만 맞추면 됩니다.
//   실제 key로 어떤 문자열을 쓰는지는 각 폴더의 README를 참고하세요.
// ============================================================

const modules = import.meta.glob('./images/**/*.{png,jpg,jpeg,svg,webp}', {
  eager: true,
  import: 'default',
});

// { agents: { '제트': '/assets/....png' }, weapons: { Vandal: '...' }, ... }
const registry = {};

for (const path in modules) {
  // path 예: "./images/agents/제트.png"
  const match = path.match(/^\.\/images\/([^/]+)\/([^/]+)\.[^.]+$/);
  if (!match) continue;
  const [, folder, name] = match;
  if (!registry[folder]) registry[folder] = {};
  registry[folder][name] = modules[path];
}

/**
 * @param {string} folder - 'agents' | 'weapons' | 'maps' | 'hitbox' | 'teams' | 'logo' | 'rating' | 'icons'
 * @param {string} key - 파일명(확장자 제외)
 * @returns {string|null} 이미지 URL 또는 파일이 없으면 null
 */
export function getAsset(folder, key) {
  return registry[folder]?.[key] ?? null;
}

export default registry;
