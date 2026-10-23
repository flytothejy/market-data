// 공통 화면 조각: 상단 메뉴·검색, 숫자 형식, 순위 목록, 표
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const CAT_KO = { cons: '컨센서스', fin: '재무', tech: '차트·수급', doc: '공시·내부자', news: '뉴스' };
const SECTOR_KO = {
  'Technology': '기술', 'Healthcare': '헬스케어', 'Financial Services': '금융', 'Consumer Cyclical': '경기소비재',
  'Consumer Defensive': '필수소비재', 'Industrials': '산업재', 'Energy': '에너지', 'Utilities': '유틸리티',
  'Real Estate': '부동산', 'Basic Materials': '소재', 'Communication Services': '커뮤니케이션',
};
const secKo = s => SECTOR_KO[s] || s || '-';

// ---- 숫자 형식
function fmtUsd(v) {
  if (v == null) return '-';
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e12) return s + '$' + (a / 1e12).toFixed(2) + '조';
  if (a >= 1e8) return s + '$' + Math.round(a / 1e8).toLocaleString() + '억';
  if (a >= 1e4) return s + '$' + (a / 1e4).toFixed(0) + '만';
  return s + '$' + a.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function fmtKrw(v) {
  if (v == null) return '-';
  if (Math.abs(v) >= 1e12) return (v / 1e12).toFixed(1) + '조원';
  if (Math.abs(v) >= 1e8) return Math.round(v / 1e8).toLocaleString() + '억원';
  if (Math.abs(v) >= 1e4) return Math.round(v / 1e4).toLocaleString() + '만원';
  return Math.round(v).toLocaleString() + '원';
}
function fmt(v, f, opt = {}) {
  if (v == null || v === '') return '-';
  switch (f) {
    case 'pct': { const x = v * 100; return (opt.sign && x > 0 ? '+' : '') + x.toFixed(Math.abs(x) < 10 ? 1 : 0) + '%'; }
    case 'pct2': return (v * 100).toFixed(2) + '%';
    case 'pctp': return (+v).toFixed(1) + '%';
    case 'x': return (+v).toFixed(v < 10 ? 1 : 0) + '배';
    case 'usd': return fmtUsd(v);
    case 'px': return '$' + (+v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case 'int': return Math.round(v).toLocaleString();
    case 'num': return (+v).toLocaleString(undefined, { maximumFractionDigits: 2 });
    case 'date': return String(v).slice(0, 10);
    default: return esc(v);
  }
}
const cls = v => v == null ? '' : v > 0 ? 'up' : v < 0 ? 'dn' : '';
const pctS = v => `<span class="${cls(v)} num">${fmt(v, 'pct', { sign: true })}</span>`;

// ---- 상단
// ---- 모바일 하단 탭 (760px 이하에서만 보임 — 위쪽 메뉴 줄 대신)
const ICON = {
  home: '<path d="M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"/>',
  map: '<circle cx="8" cy="8" r="4"/><circle cx="17" cy="7" r="2.5"/><circle cx="7" cy="17" r="2.5"/><circle cx="16.5" cy="16.5" r="3.5"/>',
  rank: '<path d="M5 20V11M12 20V5M19 20v-6"/>',
  find: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8L3.5 9.7l5.9-.9z"/>',
  more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
};
function bottomNav(active) {
  const page = ((location.pathname.split('/').pop() || 'index').replace(/\.html$/, '') || 'index') + '.html';   // Cloudflare는 .html 없는 주소로 보여 줌
  // 홈은 티커맵·랭킹 미리보기라 탭에서 빼고 로고로 (더보기에도 둠)
  const tabs = [['matrix.html', '티커맵', 'map'], ['ranking.html', '랭킹', 'rank'], ['screen.html', '검색', 'find'], ['watch.html', '후보함', 'star']];
  const more = [['index.html', '홈'], ['earnings.html', '실적 달력'], ['compare.html', '비교'], ['investors.html', '유명 투자자'], ['stock.html', '종목'], ['portfolio.html', '포트폴리오'], ['account.html', Auth.hint() ? '내 계정' : '로그인'], ['terms.html', '이용약관'], ['privacy.html', '개인정보처리방침']];
  const inMore = more.some(([h]) => h === page && h !== 'index.html') || /\/s\/|\/i\//.test(location.pathname);
  const svg = k => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${ICON[k]}</svg>`;
  const nav = document.createElement('nav');
  nav.className = 'bnav';
  nav.setAttribute('aria-label', '아래 메뉴');
  nav.innerHTML = tabs.map(([h, l, k]) => `<a href="${h}" class="${h === page ? 'on' : ''}">${svg(k)}<span>${l}</span></a>`).join('')
    + `<button class="${inMore ? 'on' : ''}" aria-expanded="false">${svg('more')}<span>더보기</span></button>`;
  const sheet = document.createElement('div');
  sheet.className = 'bsheet';
  sheet.innerHTML = `<div class="bsheet-in">${more.map(([h, l]) => `<a href="${h}" class="${h === page ? 'on' : ''}">${l}</a>`).join('')}</div>`;
  document.body.append(sheet, nav);
  const btn = nav.querySelector('button');
  const set = open => { sheet.classList.toggle('open', open); btn.setAttribute('aria-expanded', open); };
  btn.onclick = e => { e.stopPropagation(); set(!sheet.classList.contains('open')); };
  sheet.onclick = e => { if (e.target === sheet) set(false); };
}
// ---- 로그인 (구글·카카오·네이버 — Better Auth, api.tickermap.kr). 로그인 안 해도 모든 기능을 씀
// 로그인 = 이 기기의 기기코드를 계정에 묶기. 묶인 뒤에도 후보함 동기화는 기기코드로 그대로 (다른 기기에서 로그인하면 같은 후보함)
const Auth = {
  KEY: 'hub.auth.v1',
  hint() { try { return JSON.parse(localStorage.getItem(this.KEY)); } catch (e) { return null; } },   // 이름·사진만 (화면 첫 표시용)
  setHint(h) { try { h ? localStorage.setItem(this.KEY, JSON.stringify(h)) : localStorage.removeItem(this.KEY); } catch (e) { } },
  async call(path, body) {
    const r = await fetch(API_BASE + path, body === undefined ? { credentials: 'include' } : { method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (r.status === 401) { this.setHint(null); return null; }
    if (!r.ok) throw new Error(j.error || j.message || r.status);
    return j;
  },
  async me() { const j = await this.call('/api/account/me'); if (j) this.setHint({ name: j.user.name, image: j.user.image }); return j; },
  async signIn(provider) {
    const back = location.origin + '/hub/account';
    const j = await this.call('/api/auth/sign-in/social', { provider, callbackURL: back + '?login=1', newUserCallbackURL: back + '?login=1&new=1', errorCallbackURL: back + '?error=1' });
    if (j && j.url) location.href = j.url; else throw new Error('로그인 주소를 받지 못했어요');
  },
  async claim() {                                        // 로그인 직후: 이 기기를 계정에 묶고 후보함을 합침
    const j = await this.call('/api/account/claim', { code: Sync.st().code || null });
    if (j && j.code) { Sync.set({ code: j.code }); await Sync.run().catch(() => { }); }
    return j;
  },
  async signOut() {
    const code = Sync.st().code;
    try { await this.call('/api/account/forget-device', { code }); } catch (e) { }
    try { await this.call('/api/auth/sign-out', {}); } catch (e) { }
    Sync.set({ code: null, me: null, at: 0 }); this.setHint(null);   // 이 기기 후보함은 브라우저에 그대로 남음
  },
  sessions() { return this.call('/api/auth/list-sessions'); },
  revokeOthers() { return this.call('/api/auth/revoke-other-sessions', {}); },
  log() { return this.call('/api/account/log'); },
  async remove() { const j = await this.call('/api/account/delete', {}); Sync.set({ code: null, me: null, at: 0 }); this.setHint(null); return j; },
};
function acctBtn() {
  const h = Auth.hint();
  const ini = h && h.name ? esc(h.name.trim().slice(0, 1)) : '';
  return `<a class="acct" href="account.html" aria-label="${h ? '내 계정' : '로그인'}">${h ? (h.image ? `<img src="${esc(h.image)}" alt="" referrerpolicy="no-referrer">` : `<span class="acct-i">${ini || '나'}</span>`) : '<span class="acct-t">로그인</span>'}</a>`;
}
function header(active) {
  const items = [['matrix.html', '티커맵'], ['ranking.html', '티커랭킹'], ['stock.html', '종목'], ['screen.html', '검색'], ['compare.html', '비교'], ['earnings.html', '실적 달력'], ['investors.html', '유명 투자자'], ['watch.html', '후보함'], ['portfolio.html', '포트폴리오']];
  const el = document.createElement('header');
  el.className = 'top';
  el.innerHTML = `<div class="in"><a class="brand" href="index.html" aria-label="티커맵 홈"><svg width="24" height="24" viewBox="0 0 26 26" aria-hidden="true" style="flex-shrink:0"><circle cx="7.8" cy="7.8" r="6.8" fill="#d65014"/><circle cx="20.6" cy="5.4" r="4.4" fill="#2463c4"/><circle cx="21.8" cy="13.2" r="2.4" fill="#d9d6cc"/><circle cx="6.1" cy="20.9" r="4.1" fill="#7ea3dc"/><circle cx="18.2" cy="20.2" r="4.8" fill="#eba27e"/><circle cx="12.9" cy="15.3" r="1.5" fill="#d9d6cc"/></svg><span>티커맵</span></a>
  <nav class="main">${items.map(([h, l]) => `<a href="${h}" class="${l === active ? 'on' : ''}">${l}</a>`).join('')}</nav>
  <div class="search"><input type="search" placeholder="티커·회사명 (한글 가능)" aria-label="종목 검색" autocomplete="off"><div class="sugg"></div></div>${acctBtn()}</div>`;
  document.body.prepend(el);
  bottomNav(active);
  const hh = () => document.documentElement.style.setProperty('--hdr-h', el.offsetHeight + 'px');   // 따라오는 탭 줄이 헤더 바로 밑에 붙게
  hh(); addEventListener('resize', hh);
  if (Plan.isPro()) {                                  // 로그인 전 확인용 프로 미리보기 표시
    const bar = document.createElement('div');
    bar.style.cssText = 'background:var(--ink);color:var(--bg);font-size:12.5px;text-align:center;padding:6px 12px';
    const off = new URL(location.href); off.searchParams.set('pro', '0');
    bar.innerHTML = `프로 미리보기 중 — 이 브라우저에서만 프로 화면이 보입니다 · <a href="${off.href}" style="color:inherit;text-decoration:underline">끄기</a>`;
    el.after(bar);
  }
  const inp = $('input', el), box = $('.sugg', el);
  let sel = -1, list = [];
  const go = r => location.href = `${stockUrl(r.t)}`;
  inp.addEventListener('input', async () => {
    const q = inp.value.trim().toUpperCase();
    if (!q) { box.style.display = 'none'; return; }
    const u = await Data.universe();
    const ql = q.toLowerCase();
    const a = u.rows.filter(r => r.t === q), b = u.rows.filter(r => r.t !== q && r.t.startsWith(q)),
      c = u.rows.filter(r => !r.t.startsWith(q) && ((r.n || '').toLowerCase().includes(ql) || (r.ko || '').includes(inp.value.trim())));
    list = [...a, ...b.sort((x, y) => (y.mcap || y.aum || 0) - (x.mcap || x.aum || 0)), ...c.sort((x, y) => (y.mcap || y.aum || 0) - (x.mcap || x.aum || 0))].slice(0, 8);
    sel = -1;
    box.innerHTML = list.map((r, i) => `<a href="${stockUrl(r.t)}" data-i="${i}"><b>${esc(r.t)}</b><span>${r.ko ? esc(r.ko) + ' · ' : ''}${esc(r.n)}${r.k === 'etf' ? ' · ETF' : ''}</span></a>`).join('') || '<a><span>결과 없음</span></a>';
    box.style.display = 'block';
  });
  inp.addEventListener('keydown', e => {
    const as = box.querySelectorAll('a[data-i]');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = Math.max(0, Math.min(as.length - 1, sel + (e.key === 'ArrowDown' ? 1 : -1)));
      as.forEach((a, i) => a.classList.toggle('sel', i === sel));
    } else if (e.key === 'Enter') {
      if (list[sel >= 0 ? sel : 0]) go(list[sel >= 0 ? sel : 0]);
    } else if (e.key === 'Escape') box.style.display = 'none';
  });
  document.addEventListener('click', e => { if (!el.querySelector('.search').contains(e.target)) box.style.display = 'none'; });
}

async function footer() {
  const f = document.createElement('footer');
  f.className = 'foot';
  f.innerHTML = '출처: SEC EDGAR(공시·재무·내부자·13F) · FINRA(공매도 거래) · yfinance(가격·컨센서스·개요·옵션) · 공공데이터포털(국내 ETF) · 각 운용사(ETF 구성)<br>정보 제공용이며 투자 권유가 아닙니다 · <a href="terms.html">이용약관·투자 위험 고지</a> · <a href="privacy.html"><b>개인정보처리방침</b></a>';
  $('.wrap').append(f);
  try {
    const m = await Data.meta();
    f.innerHTML += `<br>가격 기준 ${esc(m.price_asof)} · 데이터 생성 ${esc(m.built.slice(0, 16).replace('T', ' '))} UTC`;
  } catch (e) { }
}

// ---- 순위 목록: rows, 값 표시 함수, 부가 표시 함수
function rankList(rows, val, sub, n = 8) {
  if (!rows.length) return '<div class="mut s13">해당 종목이 없습니다</div>';
  return `<div class="rank">${rows.slice(0, n).map((r, i) => `<a class="r" href="${stockUrl(r.t)}">
    <span class="i num">${i + 1}</span><span class="nm"><b>${esc(r.t)}</b><small>${esc(sub ? sub(r) : r.n)}</small></span><span class="v num">${val(r)}</span></a>`).join('')}</div>`;
}

function lockBox(inner, msg = '프로 멤버십에서 볼 수 있어요') {
  return `<div class="locked"><div class="blur">${inner}</div><div class="over"><span class="pro">PRO</span><b>${esc(msg)}</b></div></div>`;
}

const qs = k => new URLSearchParams(location.search).get(k);
// 종목 주소: 검색엔진용 정적 페이지 (/hub/s/NVDA/) — Pages 배포 때 hub/static_pages.py가 만듦
const stockUrl = t => `s/${encodeURIComponent(t)}/`;

// ---- 후보함 (이 브라우저에 저장 — 로그인이 붙으면 서버 저장으로 바꿈)
// 기록 하나 = 공통 스냅샷(담은 순간의 5개 렌즈 값·구역·트레일 모양·주요 지표) + 출처(어느 화면·어느 부분에서 담았나)
//   { t, at, px, purpose: 'hold'|'consider'|'watch'|'', why, note, src: {page, part, ...}, snap: {...} }
const PURPOSE = { hold: '보유 중', consider: '살까 고민', watch: '그냥 관찰' };
const Watch = {
  KEY: 'hub.watch.v2', OLD: 'hub.watch.v1',
  records() {
    try {
      let a = JSON.parse(localStorage.getItem(this.KEY));
      if (!a) {                                          // 예전 관심 종목(티커만) → 후보함으로 옮김
        const old = JSON.parse(localStorage.getItem(this.OLD)) || [];
        a = old.map(t => ({ t, at: null, px: null, purpose: '', why: '예전에 담음', note: '', src: { page: 'legacy' }, snap: null }));
        localStorage.setItem(this.KEY, JSON.stringify(a));
      }
      return a;
    } catch (e) { return this._mem || []; }
  },
  save(a, quiet) { this._mem = a; try { localStorage.setItem(this.KEY, JSON.stringify(a)); } catch (e) { } if (!quiet) Sync.soon(); },
  list() { return this.records().map(r => r.t); },
  get(t) { return this.records().find(r => r.t === t) || null; },
  has(t) { return this.list().includes(t); },
  add(rec) { const a = this.records().filter(r => r.t !== rec.t); a.unshift({ ...rec, u: Date.now() }); this.undel(rec.t); this.save(a); },
  update(t, patch) { const a = this.records(); const r = a.find(x => x.t === t); if (r) { Object.assign(r, patch, { u: Date.now() }); this.save(a); } return r; },
  remove(t) { this.tomb(t, Date.now()); this.save(this.records().filter(r => r.t !== t)); },
  toggle(t) { if (this.has(t)) { this.remove(t); return false; } this.add({ t, at: null, px: null, purpose: '', why: '', note: '', src: { page: 'unknown' }, snap: null }); return true; },
  // 지운 기록 (다른 기기에도 지워지게 동기화할 때 씀)
  DEL: 'hub.watch.del',
  dels() { try { return JSON.parse(localStorage.getItem(this.DEL)) || {}; } catch (e) { return {}; } },
  tomb(t, u) { const d = this.dels(); d[t] = u; try { localStorage.setItem(this.DEL, JSON.stringify(d)); } catch (e) { } },
  undel(t) { const d = this.dels(); if (t in d) { delete d[t]; try { localStorage.setItem(this.DEL, JSON.stringify(d)); } catch (e) { } } },
};

// ---- 후보함 동기화 + 텔레그램 알림 (Cloudflare Worker + D1)
// 이 브라우저의 기기코드(무작위)가 로그인 전 단계의 계정 역할. 코드는 이 브라우저에만 있고 서버엔 해시만 저장
// 화면은 언제나 localStorage로 바로 그리고, 바뀐 것만 뒤에서 서버와 주고받음 (항목마다 수정 시각이 더 최근인 쪽이 이김)
function notice(msg) {
  const el = document.createElement('div'); el.className = 'notice-pop'; el.textContent = msg;
  document.body.appendChild(el); setTimeout(() => el.remove(), 5000);
}
// tickermap.kr에서는 같은 사이트의 api.tickermap.kr (로그인 쿠키가 통하려면 같은 사이트여야 함), 그 밖(github.io 사본 등)은 workers.dev
const ON_SITE = /(^|\.)tickermap\.kr$/.test(location.hostname) || !!window.HUB_AUTH_TEST;
const API_BASE = (window.HUB_API || (ON_SITE ? 'https://api.tickermap.kr' : 'https://tickermap-api.flytothejy.workers.dev')).replace(/\/$/, '');
const Sync = {
  KEY: 'hub.sync.v1',
  st() { try { return JSON.parse(localStorage.getItem(this.KEY)) || {}; } catch (e) { return {}; } },
  set(p) { const s = { ...this.st(), ...p }; try { localStorage.setItem(this.KEY, JSON.stringify(s)); } catch (e) { } return s; },
  on() { return !!this.st().code; },
  async call(path, body) {
    const r = await fetch(API_BASE + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { if (r.status === 401) this.set({ code: null, me: null }); throw new Error(j.error || r.status); }
    return j;
  },
  async ensure() { if (!this.on()) this.set({ code: (await this.call('/api/register')).code }); return this.st().code; },
  _t: null,
  soon() { if (!this.on()) return; clearTimeout(this._t); this._t = setTimeout(() => this.run().catch(() => { }), 1500); },
  async run() {
    const code = this.st().code; if (!code) return null;
    const recs = Watch.records(), dels = Watch.dels();
    const items = [...recs.map(r => ({ ...r, u: r.u || (r.at ? Date.parse(r.at) : 1) })), ...Object.entries(dels).map(([t, u]) => ({ t, u, del: 1 }))];
    const j = await this.call('/api/sync', { code, items });
    // 서버 결과 반영: 서버 쪽이 더 최근이면 받아옴
    const by = Object.fromEntries(recs.map(r => [r.t, r]));
    let changed = false;
    for (const x of j.items || []) {
      const loc = by[x.t], lu = loc ? (loc.u || 0) : (dels[x.t] || -1);
      if (!(x.u > lu)) continue;
      changed = true;
      if (x.del) { delete by[x.t]; Watch.tomb(x.t, x.u); } else { by[x.t] = x; Watch.undel(x.t); }
    }
    if (changed) {
      const order = recs.map(r => r.t).filter(t => by[t]), extra = Object.keys(by).filter(t => !order.includes(t)).sort((a, b) => (by[b].u || 0) - (by[a].u || 0));
      Watch.save([...extra, ...order].map(t => by[t]), true);
      document.dispatchEvent(new CustomEvent('watch-change'));
    }
    this.set({ me: j.me, at: Date.now() });
    document.dispatchEvent(new CustomEvent('sync-change'));
    return j.me;
  },
  async link() { await this.ensure(); await this.run(); return (await this.call('/api/link', { code: this.st().code })).url; },
  async mode(m) { const j = await this.call('/api/mode', { code: this.st().code, mode: m }); this.set({ me: j.me }); return j.me; },
  async wipe() { await this.call('/api/delete', { code: this.st().code }); this.set({ code: null, me: null, at: 0 }); },
  async unlink() { const j = await this.call('/api/unlink', { code: this.st().code }); this.set({ me: j.me }); return j.me; },
  async join(token) {                                  // 텔레그램 /기기 링크 → 이 기기를 같은 후보함에 붙임 (이 기기 후보함은 합쳐짐)
    const j = await this.call('/api/join', { token });
    this.set({ code: j.code });
    return this.run();
  },
};
(() => {                                               // 페이지를 열 때 (연결된 경우만) 1분에 한 번 받아오기 + 기기 추가 링크 처리
  const m = location.hash.match(/join=([\w-]+)/);
  if (m) {
    history.replaceState(null, '', location.pathname + location.search);
    Sync.join(m[1]).then(() => notice('이 기기에 후보함을 이어 붙였어요')).catch(e => notice('기기 추가 실패: ' + e.message));
  } else if (Sync.on() && Date.now() - (Sync.st().at || 0) > 60e3) setTimeout(() => Sync.run().catch(() => { }), 300);
})();
// 포트폴리오 보유 종목 (포트폴리오 화면과 같은 저장소)
function portfolioTickers() {
  try { const p = JSON.parse(localStorage.getItem('hub.portfolio.v1')); return (p && p.items || []).map(x => x.t); } catch (e) { return []; }
}

// 렌즈 값 (티커맵 matrix.js LENS와 같은 정의) — 스냅샷·이유 문장용
const LENS_SNAP = {
  eps: { name: 'EPS 전망', max: 0.3, y: r => (r.c_chg90 != null && (r.c_n || 0) >= 3) ? r.c_chg90 : null },
  rev: { name: '매출 가속', max: 0.3, y: r => (r.rev_qg != null && r.rev_g != null) ? r.rev_qg - r.rev_g : null },
  guru: { name: '유명 투자자', max: 5, y: r => r.g13_chg ?? null },
  insider: { name: '내부자', max: 1, raw: true, y: r => { const n = (r.ib || 0) - (r.is || 0); return n ? Math.sign(n) * Math.max(0.05, Math.min(1, (Math.log10(Math.abs(n)) - 4) / 4.5)) : null; } },
  short: { name: '공매도', max: 0.08, y: r => r.sv_chg60 != null ? -r.sv_chg60 : null },
};
const QUAD_KO = { tl: '왼쪽 위', tr: '오른쪽 위', bl: '왼쪽 아래', br: '오른쪽 아래' };
const ARROW_KO = { nw: '↖', n: '↑', ne: '↗', e: '→', se: '↘', s: '↓', sw: '↙', w: '←' };
// patterns.json 값: 'st'(제자리) · 'zz'(오락가락) · [방향, 꾸준함 0~1] → '꾸준히 ↖' / '들쭉날쭉 ↖'
const patLabel = v => v == null ? null : v === 'st' ? '제자리' : v === 'zz' ? '오락가락' : Array.isArray(v) ? `${v[1] >= 0.7 ? '꾸준히' : '들쭉날쭉'} ${ARROW_KO[v[0]] || ''}` : ({ tn: '들쭉날쭉' }[v] || (ARROW_KO[v] ? '꾸준히 ' + ARROW_KO[v] : v));
function quadOf(x, yC) { return yC > 0.03 && x < -0.003 ? 'tl' : yC < -0.03 && x > 0.003 ? 'br' : yC >= 0 && x >= 0 ? 'tr' : 'bl'; }
let _pats = null;
async function patterns() { if (_pats) return _pats; try { _pats = await getJSON('free/patterns.json'); } catch (e) { _pats = {}; } return _pats; }
function snapOf(r, P) {
  // 담은 순간의 상태 (가로축은 1개월 주가 기준 구역, 트레일 모양은 1년 — EPS는 3개월)
  const lens = {};
  for (const [k, L] of Object.entries(LENS_SNAP)) {
    const y = L.y(r);
    if (y == null) continue;
    const yC = L.raw ? y : Math.max(-1, Math.min(1, y / L.max));
    const span = k === 'eps' ? '3m' : '1y';
    lens[k] = { v: +y.toFixed(4), q: r.r1m != null ? quadOf(r.r1m, yC) : null, pat: patLabel(P && P[span] && P[span][k] && P[span][k][r.t]) };
  }
  const pick = ['px', 'mcap', 'r1m', 'r3m', 'pe', 'c_fpe', 'c_upside', 'c_chg90', 'rev_g', 'om', 'sv', 'ib', 'is', 'g13', 'c_next'];
  return { lens, ...Object.fromEntries(pick.filter(k => r[k] != null).map(k => [k, r[k]])) };
}
const _p = v => v == null ? '-' : (v > 0 ? '+' : '') + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + '%';
function whyOf(src, r, snap) {
  // 출처마다 한 줄 이유 (사용자가 바꿀 수 있음)
  const L = snap && snap.lens || {};
  const lensLine = k => { const x = L[k]; if (!x) return ''; const nm = LENS_SNAP[k].name; return `${nm} ${x.pat || ''}${x.q ? ` · ${QUAD_KO[x.q]}` : ''}`.trim(); };
  switch (src.page) {
    case 'matrix': {                                   // 지도에서 보던 그대로: 고른 가로축 기간 기준 구역, 고른 트레일 길이의 모양
      const Ls = LENS_SNAP[src.lens], y = Ls && Ls.y(r);
      if (y == null) return `티커맵 ${Ls ? Ls.name : ''}`.trim();
      const yC = Ls.raw ? y : Math.max(-1, Math.min(1, y / Ls.max)), x = r[src.xw || 'r1m'];
      const pat = _pats && _pats[src.span] && _pats[src.span][src.lens] && _pats[src.span][src.lens][r.t];
      return `티커맵 ${Ls.name}${pat ? ' ' + patLabel(pat) : ''}${x != null ? ' · ' + QUAD_KO[quadOf(x, yC)] : ''}`;
    }
    case 'stock': {
      const part = src.part || 'ov';
      if (part === 'cons') return `EPS 전망 90일 ${_p(r.c_chg90)} · 목표가 여력 ${_p(r.c_upside)}`;
      if (part === 'fin') return `매출 성장 ${_p(r.rev_g)} · 영업이익률 ${_p(r.om)}`;
      if (part === 'tech') return `1개월 주가 ${_p(r.r1m)} · 공매도 비중 ${r.sv != null ? (r.sv * 100).toFixed(0) + '%' : '-'}`;
      if (part === 'doc') { const n = (r.ib || 0) - (r.is || 0); return n ? `내부자 90일 ${n > 0 ? '순매수' : '순매도'} ${fmtUsd(Math.abs(n))}` : '공시·내부자 확인'; }
      if (part === 'news') return `최근 7일 뉴스 ${r.nw7 || 0}건`;
      return r.s1 || '종목 개요';
    }
    case 'earnings': return r.c_next ? `${r.c_next.slice(5).replace('-', '/')} 실적 발표 예정` : '실적 달력';
    default: return src.label ? `${src.label}${src.part ? ' · ' + src.part : ''}` : '';
  }
}
function watchSrc(btn) {
  // 어디서 눌렀나: 화면이 window.watchSrc를 주면 그걸, 아니면 화면 이름 + 가장 가까운 카드 제목
  if (window.watchSrc) { try { const s = window.watchSrc(btn); if (s) return s; } catch (e) { } }
  const page = (location.pathname.split('/').pop() || 'index.html').replace('.html', '') || 'index';
  const label = { index: '홈', ranking: '티커랭킹', earnings: '실적 달력', compare: '비교', screen: '검색', investors: '유명 투자자', portfolio: '포트폴리오', watch: '후보함' }[page] || page;
  const h = btn.closest('.card') && btn.closest('.card').querySelector('h3');
  return { page: page === 'earnings' ? 'earnings' : page, label, part: h ? h.textContent.trim().slice(0, 30) : '' };
}
async function captureWatch(t, btn) {
  const src = watchSrc(btn);
  Stat.hit('w', t);
  Watch.add({ t, at: new Date().toISOString().slice(0, 10), px: null, purpose: '', why: '', note: '', src, snap: null });
  let r = null, P = null;
  try { const [U, pp] = await Promise.all([Data.universe(), patterns()]); r = U.rows.find(x => x.t === t); P = pp; } catch (e) { }
  if (r && Watch.has(t)) {
    const snap = snapOf(r, P);
    Watch.update(t, { px: r.px ?? null, snap, why: whyOf(src, r, snap) });
  }
  watchToast(t);
}
function watchToast(t) {
  const rec = Watch.get(t);
  if (!rec) return;
  let el = document.getElementById('watch-toast');
  if (!el) { el = document.createElement('div'); el.id = 'watch-toast'; document.body.appendChild(el); }
  el.innerHTML = `<div class="wt-top"><b>★ ${esc(t)} 후보함에 담음</b>${rec.px ? `<span class="mut">$${(+rec.px).toFixed(2)}</span>` : ''}<button class="wt-x" aria-label="닫기">×</button></div>
    <label class="wt-why"><span class="mut">담은 이유</span><input value="${esc(rec.why || '')}" maxlength="80" aria-label="담은 이유"></label>
    <div class="wt-chips">${Object.entries(PURPOSE).map(([k, l]) => `<button data-p="${k}" class="${rec.purpose === k ? 'on' : ''}">${l}</button>`).join('')}<a href="watch.html">후보함 →</a></div>`;
  el.classList.add('show');
  let timer;
  const arm = () => { clearTimeout(timer); timer = setTimeout(() => el.classList.remove('show'), 7000); };
  const hold = () => clearTimeout(timer);
  el.onmouseenter = hold; el.onmouseleave = arm; el.onfocusin = hold;
  el.querySelector('.wt-x').onclick = () => el.classList.remove('show');
  const inp = el.querySelector('.wt-why input');
  inp.onchange = () => Watch.update(t, { why: inp.value.trim() });
  el.querySelectorAll('[data-p]').forEach(b => b.onclick = () => {
    const p = rec.purpose === b.dataset.p ? '' : b.dataset.p; rec.purpose = p; Watch.update(t, { purpose: p });
    el.querySelectorAll('[data-p]').forEach(x => x.classList.toggle('on', x.dataset.p === p));
    document.dispatchEvent(new CustomEvent('watch-change'));
  });
  arm();
}

const watchBtn = t => `<button class="btn watch ${Watch.has(t) ? 'on' : ''}" data-watch="${esc(t)}" aria-pressed="${Watch.has(t)}">${Watch.has(t) ? '★ 후보함' : '☆ 후보함에 담기'}</button>`;
document.addEventListener('click', e => {
  const b = e.target.closest('[data-watch]');
  if (!b) return;
  e.preventDefault();
  const t = b.dataset.watch, on = !Watch.has(t);
  if (on) captureWatch(t, b); else Watch.remove(t);
  document.querySelectorAll(`[data-watch="${CSS.escape(t)}"]`).forEach(x => {
    x.classList.toggle('on', on); x.setAttribute('aria-pressed', on);
    if (x.classList.contains('watch')) x.textContent = on ? '★ 후보함' : '☆ 후보함에 담기';
    else x.textContent = on ? '★' : '☆';
  });
  document.dispatchEvent(new CustomEvent('watch-change'));
});
const starBtn = t => `<button class="star ${Watch.has(t) ? 'on' : ''}" data-watch="${esc(t)}" title="후보함에 담기" aria-label="${esc(t)} 후보함">${Watch.has(t) ? '★' : '☆'}</button>`;

// ---- 종목 점검표: 점수가 아니라 '확인할 거리' — 경고를 먼저, 근거 수준을 함께
// 반환: [{k, s: 'good'|'warn'|'info', t: 제목, d: 근거 한 줄, v: 내부 백테스트로 뒷받침된 신호(화면에는 표시하지 않고 정렬에만 씀)}]
function checklist(r, U) {
  if (!r) return [];
  const out = [], P = v => v == null ? '-' : (v > 0 ? '+' : '') + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + '%';
  const pp = v => (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%p';
  // 1) 티커맵 오른쪽 아래 (주가↑ 신호↓) — 검증된 경고
  const br = [];
  for (const [k, L] of Object.entries(LENS_SNAP)) {
    const y = L.y(r); if (y == null || r.r1m == null) continue;
    const yC = L.raw ? y : Math.max(-1, Math.min(1, y / L.max));
    if (quadOf(r.r1m, yC) === 'br') br.push(L.name);
  }
  if (br.length) out.push({ k: 'br', s: 'warn', v: true, t: '주가는 오르는데 신호는 꺾임', d: `티커맵 오른쪽 아래: ${br.join(', ')} (1개월 주가 ${P(r.r1m)})` });
  // 2) 이익 전망
  if (r.c_chg90 != null && (r.c_n || 0) >= 3) {
    const s = r.c_chg90 > 0.03 ? 'good' : r.c_chg90 < -0.03 ? 'warn' : 'info';
    out.push({ k: 'eps', s, t: s === 'good' ? '이익 전망 상향 중' : s === 'warn' ? '이익 전망 하향 중' : '이익 전망 큰 변화 없음', d: `내년 EPS 전망 90일 ${P(r.c_chg90)} · 30일 상향 ${r.c_up ?? 0} / 하향 ${r.c_dn ?? 0} (애널리스트 ${r.c_n}명)` });
  }
  // 3) 매출 성장 속도
  if (r.rev_qg != null && r.rev_g != null) {
    const a = r.rev_qg - r.rev_g, s = a > 0.02 ? 'good' : a < -0.05 ? 'warn' : 'info';
    out.push({ k: 'rev', s, t: s === 'good' ? '매출 성장 빨라지는 중' : s === 'warn' ? '매출 성장 느려지는 중' : '매출 성장 속도 비슷', d: `최근 분기 ${P(r.rev_qg)} vs 4개 분기 ${P(r.rev_g)} (${pp(a)})` });
  }
  // 4) 수익성
  if (r.om_chg != null && r.om != null) {
    const s = r.om_chg > 0.02 ? 'good' : r.om_chg < -0.03 ? 'warn' : 'info';
    out.push({ k: 'om', s, t: s === 'good' ? '이익률 개선' : s === 'warn' ? '이익률 악화' : '이익률 비슷', d: `영업이익률 ${(r.om * 100).toFixed(1)}% (1년 전보다 ${pp(r.om_chg)})` });
  }
  // 5) 내부자 — 순매수는 검증된 신호, 매도는 세금·계획 매도가 많아 시총 대비 클 때만 경고
  const net = (r.ib || 0) - (r.is || 0);
  if (r.ib >= 1e5) out.push({ k: 'ins', s: 'good', v: true, t: '임원 장내 매수', d: `최근 90일 매수 ${fmtUsd(r.ib)}${r.ibn ? ` (${r.ibn}명)` : ''}${r.is ? ` · 매도 ${fmtUsd(r.is)}` : ''}` });
  else if (r.is && r.mcap && r.is / r.mcap > 0.005) out.push({ k: 'ins', s: 'warn', t: '내부자 매도 많음', d: `최근 90일 매도 ${fmtUsd(r.is)} (시가총액의 ${(r.is / r.mcap * 100).toFixed(1)}%)` });
  else if (r.is || r.ib) out.push({ k: 'ins', s: 'info', t: '내부자 거래 특이 사항 없음', d: `최근 90일 순${net >= 0 ? '매수' : '매도'} ${fmtUsd(Math.abs(net))}` });
  // 6) 유명 투자자 (13F, 분기 늦음)
  if (r.g13_chg != null && (r.g13 || r.g13_chg)) {
    const s = r.g13_chg >= 2 ? 'good' : r.g13_chg <= -2 ? 'warn' : 'info';
    out.push({ k: 'guru', s, t: s === 'good' ? '유명 투자자 매수 우위' : s === 'warn' ? '유명 투자자 매도 우위' : '유명 투자자 변화 적음', d: `보유 ${r.g13 ?? 0}곳 · 순증 ${r.g13_chg > 0 ? '+' : ''}${r.g13_chg}${r.g13_new ? ` · 신규 ${r.g13_new}곳` : ''} (13F, 분기 말 기준)` });
  }
  // 7) 공매도
  if (r.sv_chg60 != null) {
    const s = r.sv_chg60 > 0.03 || (r.si || 0) > 0.15 ? 'warn' : r.sv_chg60 < -0.03 ? 'good' : 'info';
    out.push({ k: 'short', s, t: s === 'warn' ? '공매도 늘어남' : s === 'good' ? '공매도 줄어듦' : '공매도 변화 적음', d: `거래 비중 60일 ${pp(r.sv_chg60)}${r.si != null ? ` · 공매도 잔고 ${(r.si * 100).toFixed(1)}%` : ''}` });
  }
  // 8) 밸류 — 같은 업종 선행 PER 중간값과 비교
  if (r.c_fpe > 0 && U) {
    const xs = U.rows.filter(x => x.k === 'stock' && x.sec === r.sec && x.c_fpe > 0).map(x => x.c_fpe).sort((a, b) => a - b);
    if (xs.length >= 8) {
      const med = xs[Math.floor(xs.length / 2)], k = r.c_fpe / med, s = k > 1.5 ? 'warn' : k < 0.7 ? 'good' : 'info';
      out.push({ k: 'val', s, t: s === 'warn' ? '업종보다 비쌈' : s === 'good' ? '업종보다 쌈' : '업종과 비슷한 가격', d: `선행 PER ${r.c_fpe.toFixed(1)}배 · ${secKo(r.sec)} 중간값 ${med.toFixed(1)}배` });
    }
  }
  // 9) 추세
  if (r.d200 != null) out.push({ k: 'trend', s: r.d200 < -0.1 ? 'warn' : r.d200 > 0 ? 'good' : 'info', t: r.d200 >= 0 ? '200일선 위' : '200일선 아래', d: `200일 평균 대비 ${P(r.d200)} · 52주 고가 대비 ${P(r.hi52)}` });
  // 10) 실적 일정 (좋고 나쁨이 아니라 변동 위험)
  if (r.c_next) {
    const dd = Math.round((new Date(r.c_next + 'T12:00:00Z') - Date.now()) / 864e5);
    if (dd >= 0 && dd <= 21) out.push({ k: 'er', s: 'info', t: `실적 발표 ${dd === 0 ? '오늘' : dd + '일 뒤'}`, d: `${r.c_next}${r.er_imp ? ` · 옵션 예상 변동 ±${(r.er_imp * 100).toFixed(1)}%` : ''}${r.er_avg ? ` · 최근 8번 평균 ±${(r.er_avg * 100).toFixed(1)}%` : ''}` });
  }
  const order = { warn: 0, good: 1, info: 2 };
  return out.sort((a, b) => order[a.s] - order[b.s] || (b.v ? 1 : 0) - (a.v ? 1 : 0));
}
function checklistHtml(items, compact) {
  if (!items.length) return '';
  const n = s => items.filter(x => x.s === s).length;
  const ic = { warn: ['⚠', 'var(--warn)'], good: ['✓', 'var(--good)'], info: ['·', 'var(--muted)'] };
  const rows = (compact ? items.filter(x => x.s !== 'info') : items).map(x => `<div class="ck-row"><span class="ck-ic" style="color:${ic[x.s][1]}">${ic[x.s][0]}</span><div><b>${esc(x.t)}</b><div class="small mut">${esc(x.d)}</div></div></div>`).join('');
  return `<div class="ck"><div class="ck-head"><b>종목 점검표</b><span class="s13"><span style="color:var(--warn)">경고 ${n('warn')}</span> · <span style="color:var(--good)">우호 ${n('good')}</span> · <span class="mut">참고 ${n('info')}</span></span></div>
    <div class="ck-list">${rows || '<div class="small mut">경고·우호 신호 없음</div>'}</div>
    <div class="small faint">점수나 추천이 아니라 확인할 거리예요</div></div>`;
}

// ---- 최근 실적 결과 (build.py er_result) — 종목 화면·후보함에서 같이 씀
function erResultHtml(L, opt = {}) {
  if (!L) return '';
  const md = s => s ? `${+s.slice(5, 7)}/${+s.slice(8, 10)}` : '';
  const usd = v => v == null ? '-' : Math.abs(v) >= 1e6 ? fmtUsd(v) : '$' + v.toFixed(2);
  const vs = (x, unit) => x ? `<b class="num">${usd(x.a)}</b> ${pb(x.s)}<span class="mut s13">예상 ${usd(x.e)}</span>` : `<span class="mut s13">${unit}</span>`;
  const pb = v => `<b class="${cls(v)} num">${fmt(v, 'pct', { sign: true })}</b>`;
  const big = L.mv != null && L.avg ? Math.abs(L.mv) > 1.5 * L.avg : false;
  const head = [L.verdict, L.guide].filter(Boolean).join(' · ');
  const after = L.days >= 1 && (L.nq || L.fy != null || L.pt != null);
  return `<div class="er-res">
    <div class="er-h"><b>${head ? esc(head) : '결과 집계 중'}</b><span class="mut s13">${md(L.d)} 발표${L.q ? ` · ${esc(L.q.slice(0, 7))} 분기` : ''}</span></div>
    <div class="kv">
      <div><span>EPS</span>${vs(L.eps, '집계 중 (보통 발표 다음 날)')}</div>
      <div><span>매출</span>${vs(L.rev, '집계 중 (분기 보고서 제출 뒤)')}</div>
      <div><span>발표 다음 날${L.mv_d ? `(${md(L.mv_d)})` : ''} 주가</span>${L.mv != null ? `${pb(L.mv)}<span class="mut s13">평소 ±${fmt(L.avg, 'pct')}${L.n_hist && L.n_hist < 4 ? ` (발표 ${L.n_hist}번)` : ''}${big ? ' · 평소보다 큼' : ''}</span>` : '<span class="mut s13">다음 거래일 종가 뒤</span>'}</div>
      ${L.since != null && L.mv != null && Math.abs(L.since - L.mv) >= 0.02 ? `<div><span>발표 전 대비 지금</span>${pb(L.since)}<span class="mut s13">${esc((L.since_d || '').slice(5).replace('-', '/'))} 종가</span></div>` : ''}
    </div>
    ${after ? `<div class="er-after"><div class="small mut">발표 뒤 애널리스트 전망 변화 (발표 전 대비 · ${L.days}거래일째)</div>
      <div class="kv">${L.nq && L.nq.rev != null ? `<div><span>다음 분기 매출 전망</span>${pb(L.nq.rev)}</div>` : ''}${L.nq && L.nq.eps != null ? `<div><span>다음 분기 EPS 전망</span>${pb(L.nq.eps)}</div>` : ''}${L.fy != null ? `<div><span>올해 EPS 전망</span>${pb(L.fy)}</div>` : ''}${L.pt != null ? `<div><span>평균 목표가</span>${pb(L.pt)}</div>` : ''}${L.up7 != null || L.dn7 != null ? `<div><span>최근 7일 상향·하향</span><b class="num">${L.up7 ?? 0} · ${L.dn7 ?? 0}</b></div>` : ''}</div></div>`
      : L.eps ? '<div class="small faint">발표 뒤 애널리스트 전망 변화는 다음 갱신부터 보여요</div>' : ''}
    ${opt.note === false ? '' : '<div class="small faint">예상 = 발표 전날까지의 애널리스트 평균 · 가이던스 원문 대신 발표 뒤 애널리스트가 고친 전망으로 회사 전망의 온도를 봐요</div>'}
  </div>`;
}

// ---- 지표 설명 (라벨 옆 ? 에 마우스를 올리거나 누르면 표시)
const GLOSS = {
  c_ratio: '최근 30일 동안 내년 EPS 전망을 올린 애널리스트 수에서 내린 수를 빼고, 전체 수로 나눈 값. 플러스면 전망이 좋아지는 중',
  c_up: '최근 30일 동안 내년 EPS 전망을 올린 애널리스트 수', c_dn: '최근 30일 동안 내년 EPS 전망을 내린 애널리스트 수',
  c_chg90: '90일 전과 비교한 내년 EPS 전망치의 변화율',
  c_upside: '애널리스트 평균 목표가가 지금 주가보다 얼마나 높은지',
  c_buy: '매수·적극 매수 의견을 낸 애널리스트의 비중',
  c_fpe: '지금 주가 ÷ 내년 EPS 전망. 미래 이익 기준으로 몇 년 치 이익만큼의 가격인지',
  c_surp: '직전 분기 실제 EPS가 전망치보다 얼마나 높았는지(+) 낮았는지(−)',
  c_beats: '최근 4개 분기 중 실제 EPS가 전망치를 넘은 횟수',
  c_next: '회사가 발표했거나 예상되는 다음 실적 발표일 (미국 동부 기준)',
  er_avg: '최근 8번의 실적 발표 때 주가가 위아래로 평균 얼마나 움직였는지 (발표 전날 종가 → 다음 날 종가, 방향 무시)',
  er_imp: '발표 직후 끝나는 옵션 가격이 예상하는 발표 전후 주가 변동폭(±1 표준편차, 약 68% 확률 범위). 만기까지 섞인 평소 거래일의 변동은 빼고 계산. 발표 주간에만 표시',
  rev: '최근 4개 분기 매출 합계 (SEC 제출 재무제표 기준)', rev_g: '최근 4개 분기 매출 합계를 1년 전 같은 기간과 비교',
  rev_qg: '가장 최근 분기 매출을 1년 전 같은 분기와 비교',
  gm: '매출에서 원가를 뺀 매출총이익이 매출의 몇 %인지. 높을수록 가격 결정력이 강한 편',
  om: '본업에서 남긴 영업이익이 매출의 몇 % 인지 (최근 4개 분기 합계 기준)',
  om_chg: '영업이익률이 1년 전보다 몇 %p 바뀌었는지', nm: '최종 순이익이 매출의 몇 %인지',
  ni_g: '최근 4개 분기 순이익 합계를 1년 전과 비교', eps: '주당 순이익. 최근 4개 분기 합계',
  fcf: '영업으로 번 현금에서 설비투자를 뺀 돈. 배당·자사주 매입·부채 상환에 쓸 수 있는 현금',
  roe: '순이익 ÷ 자기자본. 주주 돈으로 1년에 얼마를 벌었는지', roa: '순이익 ÷ 총자산',
  de: '장기부채 ÷ 자기자본. 높을수록 빚에 많이 기댐', cr: '유동자산 ÷ 유동부채. 1보다 크면 1년 안에 갚을 빚보다 1년 안에 현금화할 자산이 많음',
  rnd: '연구개발비가 매출의 몇 %인지',
  pe: '시가총액 ÷ 최근 4개 분기 순이익. 지금 이익 기준으로 몇 년 치 이익만큼의 가격인지',
  ps: '시가총액 ÷ 최근 4개 분기 매출', pb: '시가총액 ÷ 자기자본',
  fcfy: '잉여현금흐름 ÷ 시가총액. 주식을 산다면 받는 현금 수익률에 가까움', dy: '최근 12개월 배당금 ÷ 지금 주가',
  shy: '(최근 4개 분기 배당 + 자사주 매입) ÷ 시가총액',
  r12_1: '최근 1개월을 뺀 12개월 수익률. 모멘텀 투자에서 많이 쓰는 지표',
  d50: '지금 주가가 50일 이동평균보다 몇 % 위(+)·아래(−)인지', d200: '지금 주가가 200일 이동평균보다 몇 % 위(+)·아래(−)인지',
  rsi: '최근 14일 상승폭과 하락폭으로 만든 0~100 지표. 70 이상은 과열, 30 이하는 과매도로 흔히 봄',
  hi52: '지금 주가가 52주 최고가보다 몇 % 낮은지', lo52: '지금 주가가 52주 최저가보다 몇 % 높은지',
  vr: '최근 20일 평균 거래량 ÷ 최근 120일 평균 거래량. 1보다 크면 거래가 늘어난 것',
  vol: '최근 60일 일간 수익률의 표준편차를 연 단위로 바꾼 값',
  gc: '50일 이동평균이 200일 이동평균을 위로 뚫은 가장 최근 날짜',
  sv: 'FINRA에 보고된 공매도 거래량 ÷ 전체 거래량 (최근 20거래일 평균). 시장조성 거래가 섞여 있어 보통 40~50%대',
  si: '빌려서 판 뒤 아직 갚지 않은 주식 수가 유통주식의 몇 %인지 (한 달에 두 번 공개)',
  iv: '옵션 가격에서 거꾸로 계산한, 앞으로 30일의 연 환산 예상 변동성',
  pcr: '풋옵션 거래량 ÷ 콜옵션 거래량. 높을수록 하락에 대비하는 거래가 많음',
  skew: '10% 아래 풋옵션 변동성 − 10% 위 콜옵션 변동성. 클수록 급락을 더 걱정하는 상태',
  ib: '최근 90일 임원·이사가 장내에서 산 금액 (Form 4)', is: '최근 90일 임원·이사가 장내에서 판 금액 (Form 4)',
  ibn: '최근 90일 장내 매수한 내부자 수', f144: '최근 30일 내부자 등이 주식을 팔겠다고 미리 낸 신고 건수',
  rf_new: '올해 10-K 위험요인 문장 중 작년 어떤 문장과도 닮지 않은 문장의 비율. 높으면 새 위험을 많이 적은 것',
  rf_sim: '올해와 작년 10-K 위험요인의 단어 유사도 (1 = 같음)', md_unc: '경영진 논의에서 불확실성 단어(may, uncertain 등)의 비율',
  g13: '추적 중인 유명 투자자(집중 투자형·행동주의 약 36곳) 중 이 종목을 보유한 곳의 수. 분기 13F 기준이며 대형 운용사·퀀트 펀드는 세지 않음',
  g13_chg: '이번 분기 새로 사거나 5% 넘게 늘린 유명 투자자 수 − 다 팔거나 5% 넘게 줄인 수',
};
const tip = k => GLOSS[k] ? `<span class="tip" tabindex="0" role="note" aria-label="${esc(GLOSS[k])}" data-tip="${esc(GLOSS[k])}">?</span>` : '';

// ---- 티커에 마우스를 올리면 회사 이름 (화면 어디든: 표·범례·칩·순위 목록)
// 글자가 티커 모양인 가장 안쪽 요소를 찾아 표시해 두고, 올렸을 때 종목 목록에서 찾아 보여 줌 (없으면 아무것도 안 함)
(() => {
  const RE = /^[A-Z][A-Z0-9.\-]{0,6}$/;
  const SEL = 'b,strong,a,th,td,span,button,small,i,em,div,label';
  let map = null, loading = null;
  const load = () => loading || (loading = Data.universe().then(U => { map = new Map(U.rows.map(r => [r.t, r])); }).catch(() => { map = new Map(); }));
  function tag(root) {
    if (!root || !root.querySelectorAll) return;
    const els = root.matches && root.matches(SEL) ? [root, ...root.querySelectorAll(SEL)] : root.querySelectorAll(SEL);
    for (const el of els) {
      if (el.dataset.tk || el.closest('svg,input,textarea,select,nav,.tk-tip,[data-notk]')) continue;
      const t = el.textContent.trim();
      if (t.length > 7 || !RE.test(t)) continue;
      if ([...el.children].some(c => c.textContent.trim())) continue;       // 글자를 가진 자식이 있으면 그 자식이 대상
      if (!map.has(t)) continue;
      el.dataset.tk = t;
    }
  }
  let pend = [], timer = null;
  const mo = new MutationObserver(ms => {
    for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) pend.push(n);
    clearTimeout(timer); timer = setTimeout(() => { const a = pend; pend = []; a.forEach(tag); }, 120);
  });
  const start = () => load().then(() => { tag(document.body); mo.observe(document.body, { childList: true, subtree: true }); });   // 화면 대부분이 이미 받는 목록 (캐시 공유)
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);

  let tip = null, cur = null;
  const hide = () => { if (tip) tip.style.display = 'none'; cur = null; };
  document.addEventListener('mouseover', async e => {
    const el = e.target.closest && e.target.closest('[data-tk]');
    if (!el || el === cur) return;
    cur = el;
    const r = map && map.get(el.dataset.tk);
    if (!r) return;
    if (!tip) { tip = document.createElement('div'); tip.className = 'tk-tip'; document.body.appendChild(tip); }
    const sub = r.k === 'etf'
      ? [r.grp, r.aum ? `운용자산 ${fmtUsd(r.aum)}` : '', r.exp != null ? `보수 ${(r.exp * 100).toFixed(2)}%` : ''].filter(Boolean).join(' · ')
      : [r.sec ? secKo(r.sec) : '', r.mcap ? `시가총액 ${fmtUsd(r.mcap)}` : ''].filter(Boolean).join(' · ');
    tip.innerHTML = `<div><b>${esc(r.t)}</b> ${esc(r.ko || '')}</div>${r.n && r.n !== r.ko ? `<div class="tk-n">${esc(r.n)}</div>` : ''}${sub ? `<div class="tk-s">${esc(sub)}${r.r1d != null ? ` · 1일 <span class="${cls(r.r1d)}">${fmt(r.r1d, 'pct', { sign: true })}</span>` : ''}</div>` : ''}`;
    tip.style.display = 'block';
    const b = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let x = Math.min(Math.max(8, b.left + b.width / 2 - w / 2), innerWidth - w - 8), y = b.top - h - 8;
    if (y < 8) y = b.bottom + 8;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  });
  document.addEventListener('mouseout', e => { const el = e.target.closest && e.target.closest('[data-tk]'); if (el && el === cur && !el.contains(e.relatedTarget)) hide(); });
  addEventListener('scroll', hide, { passive: true });
})();

// ---- 앱처럼 설치(PWA): 서비스 워커 등록 (https에서만)
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  addEventListener('load', () => navigator.serviceWorker.register(new URL('sw.js', document.baseURI).href).catch(() => { }));
}

// ---- 종목별 이용 집계 (개인 식별 없음 — 종목·종류만 보냄. 같은 기기·종목·종류는 하루 한 번)
const Stat = {
  KEY: 'hub.stat.v1', q: [], t: null,
  hit(k, t) {
    if (!t || navigator.webdriver || (location.protocol !== 'https:' && !window.HUB_STAT_TEST)) return;
    const day = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
    let st; try { st = JSON.parse(localStorage.getItem(this.KEY)) || {}; } catch (e) { return; }
    if (st.d !== day) st = { d: day, k: [] };
    const key = k + ':' + t;
    if (st.k.includes(key)) return;
    st.k.push(key);
    try { localStorage.setItem(this.KEY, JSON.stringify(st)); } catch (e) { return; }
    this.q.push([k, t]);
    clearTimeout(this.t); this.t = setTimeout(() => this.flush(), 1500);
  },
  flush() {
    if (!this.q.length) return;
    const body = JSON.stringify({ e: this.q.splice(0, 20) });
    try { if (!(navigator.sendBeacon && navigator.sendBeacon(API_BASE + '/api/ev', body))) fetch(API_BASE + '/api/ev', { method: 'POST', body, keepalive: true }).catch(() => { }); } catch (e) { }
  },
};
addEventListener('pagehide', () => Stat.flush());
let _pop = null;
async function popularStats() {   // 최근 7일·30일 종목별 합계 {d7: {T: {v,w,c,a}}, d30, tot7}
  if (_pop) return _pop;
  _pop = fetch(API_BASE + '/api/popular').then(r => r.ok ? r.json() : null).catch(() => null);
  return _pop;
}
