import { useCallback, useEffect, useState } from 'react';

const STORAGE_PREFIX = 'cooldown_';

function readLastTrigger(key) {
  const raw = localStorage.getItem(STORAGE_PREFIX + key);
  return raw ? Number(raw) : 0;
}

/**
 * key별로 마지막 클릭 시각을 localStorage에 저장하고, durationMs가 지나기 전까지
 * isReady=false를 반환하는 쿨다운 훅 (예: 전적갱신 버튼 5분 쿨다운).
 */
export function useCooldown(key, durationMs = 5 * 60 * 1000) {
  const [lastTrigger, setLastTrigger] = useState(() => readLastTrigger(key));
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setLastTrigger(readLastTrigger(key));
  }, [key]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const remainingMs = Math.max(0, lastTrigger + durationMs - now);
  const isReady = remainingMs === 0;

  const trigger = useCallback(() => {
    const ts = Date.now();
    localStorage.setItem(STORAGE_PREFIX + key, String(ts));
    setLastTrigger(ts);
    setNow(ts);
  }, [key]);

  return { isReady, remainingMs, trigger };
}
