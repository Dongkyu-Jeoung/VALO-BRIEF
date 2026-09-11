import { useEffect, useState } from 'react';

// 모듈 레벨 캐시 - 컴포넌트가 여러 번 마운트돼도(맵 탭 전환 등) 이 앱 세션 안에서는
// /api/maps/minimaps 요청이 딱 한 번만 나가게 한다. 서버(map_coords_service.py)도
// 이미 자체 캐시가 있어 valorant-api.com 호출은 서버 프로세스당 1회뿐이니, 프론트까지
// 합치면 사실상 "매번 API를 두드리는" 상황이 되지 않는다.
let cachedUrls = null;
let inflightPromise = null;

async function fetchMinimapUrls() {
  if (cachedUrls) return cachedUrls;
  if (!inflightPromise) {
    // 다른 API 호출들과 동일하게 VITE_API_BASE_URL을 붙인다 - 상대 경로("/api/...")로
    // 요청하면 프론트 개발 서버(Vite) 자신에게 요청이 가서 index.html이 돌아오는
    // 문제가 있었다(2026-09-11 확인, vite.config.js에 프록시 설정이 없음).
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
    inflightPromise = fetch(`${baseUrl}/api/maps/minimaps`)
      .then((res) => {
        if (!res.ok) throw new Error(`minimap url fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        cachedUrls = data;
        return data;
      })
      .catch((err) => {
        // 실패해도 조용히 넘어간다 - 호출부(DeathMapTracker)가 기존 로컬 이미지로
        // 폴백해야 하므로 빈 객체를 캐시해서 이후 재시도로 요청이 반복되지 않게 한다.
        console.error('[useMinimapUrls] 공식 미니맵 URL을 못 가져왔습니다 - 로컬 이미지로 대체합니다.', err);
        cachedUrls = {};
        return cachedUrls;
      });
  }
  return inflightPromise;
}

/**
 * mapId(영문 소문자, gameData.maps[].id와 동일)에 해당하는 공식 미니맵 이미지 URL을
 * 반환한다. 아직 못 받아왔거나(로딩 중) 서버에 없는 맵이면 undefined를 반환하니,
 * 호출부는 반드시 로컬 이미지 등으로 폴백 처리해야 한다.
 */
export function useMinimapUrl(mapId) {
  const [url, setUrl] = useState(cachedUrls?.[mapId]);

  useEffect(() => {
    let active = true;
    fetchMinimapUrls().then((urls) => {
      if (active) setUrl(urls[mapId]);
    });
    return () => {
      active = false;
    };
  }, [mapId]);

  return url;
}