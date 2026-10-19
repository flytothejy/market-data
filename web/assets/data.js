// 데이터 모듈 — 화면은 이 파일을 통해서만 데이터를 읽음.
// 나중에 Cloudflare/Supabase로 옮길 때 API 주소(또는 아래 함수 내부)만 바꾸면 됨.
const API = new URL('../api/v1/', location.href).href;

const _cache = new Map();
function getJSON(path) {
  if (!_cache.has(path)) {
    _cache.set(path, fetch(API + path, { cache: 'no-cache' }).then(r => {
      if (!r.ok) throw new Error(path + ' ' + r.status);
      return r.json();
    }).catch(e => { _cache.delete(path); throw e; }));
  }
  return _cache.get(path);
}

// 등급: 지금은 모두 무료 사용자. 로그인·결제가 붙으면 여기서 판단
const Plan = { isPro: () => false, PORTFOLIO_MAX: 10 };

const Data = {
  meta: () => getJSON('meta.json'),
  universe: () => getJSON('free/universe.json'),
  market: () => getJSON('free/market.json'),
  stock: t => getJSON(`free/stock/${encodeURIComponent(t)}.json`),
  stockPro: t => Plan.isPro() ? getJSON(`pro/stock/${encodeURIComponent(t)}.json`) : Promise.resolve(null),
  etf: t => getJSON(`free/etf/${encodeURIComponent(t)}.json`),
  krEtfs: () => getJSON('free/kr_etf.json'),
  krEtf: code => getJSON(`free/kr_etf/${encodeURIComponent(code)}.json`),
};
