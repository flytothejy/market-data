// 티커맵 서비스 워커 — 앱처럼 설치·빠른 재방문·오프라인일 때 마지막으로 본 화면
// 배포 때 __V__가 커밋으로 바뀌어 새 버전이 나오면 캐시를 새로 만듦
const V = '__V__';
const SHELL = `shell-${V}`, DATA = 'data-v1';
const PRE = ['./', 'offline.html', 'assets/app.css', 'assets/data.js', 'assets/ui.js', 'assets/icon.svg', 'manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(PRE.map(u => new Request(u, { cache: 'reload' })))).catch(() => { }));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('shell-') && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

const put = (name, req, res) => {
  if (res && res.ok) {
    const c = res.clone();
    caches.open(name).then(async x => {
      await x.put(req, c);
      if (name === DATA) { const ks = await x.keys(); for (const k of ks.slice(0, Math.max(0, ks.length - 300))) x.delete(k); }   // 종목 파일은 최근 300개만
    });
  }
  return res;
};

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;            // 알림 API(Worker) 등 다른 주소는 건드리지 않음
  // 화면 데이터(/api/): 언제나 새로 받고, 안 되면 마지막에 받은 것
  if (url.pathname.includes('/api/v1/')) {
    e.respondWith(fetch(req).then(r => put(DATA, req, r)).catch(() => caches.match(req)));
    return;
  }
  // 페이지: 새로 받고, 안 되면 저장해 둔 것 → 그것도 없으면 오프라인 안내
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(r => put(SHELL, req, r)).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('offline.html'))));
    return;
  }
  // 스크립트·스타일·그림: 저장해 둔 것을 바로 쓰고 뒤에서 새로 받아 둠 (주소에 버전이 붙어 있어 바뀐 파일은 새 주소)
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(r => put(SHELL, req, r)).catch(() => hit);
    return hit || net;
  }));
});
