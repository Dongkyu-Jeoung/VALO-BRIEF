const modules = import.meta.glob('./images/**/*.{png,jpg,jpeg,svg,webp}', {
  eager: true,
  import: 'default',
});

const registry = {};

for (const path in modules) {
  const match = path.match(/^\.\/images\/([^/]+)\/([^/]+)\.[^.]+$/);
  if (!match) continue;
  const [, folder, rawName] = match;
  const name = rawName.toLowerCase();

  if (!registry[folder]) registry[folder] = {};
  registry[folder][name] = modules[path];
}

export function getAsset(folder, key) {
  if (!key) return null;
  const lowerKey = key.toLowerCase();
  const result = registry[folder]?.[lowerKey] ?? null;

  return result;
}

export default registry;