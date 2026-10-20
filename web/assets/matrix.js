// 어긋남 지도 — 가로 = 주가(기간 선택), 세로 = 신호(렌즈), 점 크기 = 시가총액
// 신호와 주가가 반대로 간 왼쪽 위·오른쪽 아래가 핵심. 휠·드래그로 확대·이동, 점을 누르면 궤적(지나온 길)
header('지도');
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const XW = { r1w: ['1주', 0.12], r1m: ['1개월', 0.3], r3m: ['3개월', 0.5], r6m: ['6개월', 0.7] };
const XI = { r1w: 1, r1m: 2, r3m: 3, r6m: 4 };          // 궤적 점 [날짜, 1주, 1개월, 3개월, 6개월, 신호]
const money = v => { const a = Math.abs(v); return a >= 1e8 ? '$' + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + '억' : a >= 1e4 ? '$' + Math.round(a / 1e4) + '만' : '$' + Math.round(a); };
const sgn = (v, d = 0) => (v > 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
const LENS = {
  eps: {
    name: 'EPS 전망', max: 0.3, y: r => (r.c_chg90 != null && (r.c_n || 0) >= 3) ? r.c_chg90 : null, fy: v => '전망 ' + sgn(v, Math.abs(v) < 0.1 ? 1 : 0),
    up: '내년 EPS 전망 상향', dn: '전망 하향', tl: '전망은 오르는데 주가는 빠짐', br: '주가는 오르는데 전망은 꺾임', trail: 'eps',
    desc: '세로 = 애널리스트들의 내년 EPS(주당순이익) 전망이 90일 전보다 얼마나 바뀌었나. 왼쪽 위는 이익 전망이 좋아지는데 주가가 빠진 종목입니다.',
  },
  rev: {
    name: '매출 가속', max: 0.3, y: r => (r.rev_qg != null && r.rev_g != null) ? r.rev_qg - r.rev_g : null, fy: v => '가속 ' + (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%p',
    up: '매출 성장 가속', dn: '매출 성장 둔화', tl: '매출 성장은 빨라지는데 주가는 빠짐', br: '주가는 오르는데 매출 성장은 둔화', trail: 'rev',
    desc: '세로 = 최근 분기 매출 성장률(1년 전 같은 분기 대비)에서 최근 4개 분기 합계 성장률을 뺀 값. 플러스면 성장이 빨라지는 중입니다. SEC 재무제표 기준.',
  },
  guru: {
    name: '유명 투자자', max: 5, jitter: true, y: r => r.g13_chg ?? null, fy: v => '투자자 ' + (v > 0 ? '+' : '') + (Number.isInteger(v) ? v : v.toFixed(1)) + '곳',
    up: '유명 투자자 순매수', dn: '순매도', tl: '유명 투자자는 사는데 주가는 빠짐', br: '주가는 오르는데 유명 투자자는 팖', trail: 'guru',
    desc: '세로 = 유명 투자자 36곳 중 이번 분기 새로 사거나 늘린 곳 − 팔거나 줄인 곳 (13F). 13F는 분기 말 기준이라 최대 4개월 반 늦은 정보예요.',
  },
  insider: {
    name: '내부자', max: 1, raw: true,
    y: r => { const n = (r.ib || 0) - (r.is || 0); return n ? Math.sign(n) * Math.max(0.05, Math.min(1, (Math.log10(Math.abs(n)) - 4) / 4.5)) : null; },
    fy: (v, r) => { if (!r) return (v > 0 ? '순매수 쪽 ' : '순매도 쪽 ') + Math.abs(v).toFixed(2); const n = (r.ib || 0) - (r.is || 0); return (n > 0 ? '순매수 ' : '순매도 ') + money(n); },
    up: '내부자 순매수 (금액, 로그)', dn: '순매도', tl: '내부자는 사는데 주가는 빠짐', br: '주가는 오르는데 내부자는 팖', trail: null,
    desc: '세로 = 최근 90일 임원·이사의 장내 매수 − 매도 금액 (Form 4, 로그 눈금). 매도는 세금·계획 매도가 많아 매수 쪽 신호가 더 의미 있어요.',
  },
  short: {
    name: '공매도', max: 0.12, y: r => r.sv_chg != null ? -r.sv_chg : null, fy: v => '공매도 ' + (-v > 0 ? '+' : '') + (-v * 100).toFixed(1) + '%p',
    up: '공매도 감소', dn: '공매도 증가', tl: '공매도는 줄었는데 주가는 빠짐', br: '주가는 오르는데 공매도는 늘어남', trail: 'short',
    desc: '세로 = 공매도 거래 비중(최근 20거래일)이 직전 20거래일보다 얼마나 줄었나. 오른쪽 아래는 주가가 오르는 동안 하락에 거는 거래가 늘어난 종목입니다.',
  },
};
const VIEWS = { stock: '종목', sec: '업종', ind: '세부 업종' };
const TRACK_COL = ['var(--ink)', '#7c3aed', '#0f766e', '#b45309', '#be185d'];
const FULL = [-1.04, 1.04, -1.04, 1.04];
const st = {
  lens: LENS[qs('lens')] ? qs('lens') : 'eps', xw: XW[qs('x')] ? qs('x') : 'r1m', sec: qs('sec') || '', cap: +(qs('cap') || 0),
  only: qs('only') || '', view: VIEWS[qs('view')] ? qs('view') : 'stock', track: (qs('t') || '').split(',').filter(Boolean).slice(0, 5),
  onlyTrack: qs('focus') === '1', dom: FULL.slice(), trail: {},
};
let U, S, W = 900, H = 640, P = [], GT = null, drawQueued = false, sideTimer = null;
const PAD = { l: 54, r: 18, t: 44, b: 40 };

const nyToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const addDays = (s, n) => { const d = new Date(s + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
function weekRange() { const t = nyToday(), dw = new Date(t + 'T12:00:00Z').getUTCDay(), m = addDays(t, -((dw + 6) % 7)); return [m, addDays(m, 6)]; }
const hash = s => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 997; return h / 997 - 0.5; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const isGroup = id => id.startsWith('sec:') || id.startsWith('ind:');
const groupName = id => id.slice(4);
const labelOf = id => id.startsWith('sec:') ? secKo(groupName(id)) : id.startsWith('ind:') ? groupName(id) : id;

function sync() {
  const u = new URL(location.href);
  const set = (k, v, d) => v && v !== d ? u.searchParams.set(k, v) : u.searchParams.delete(k);
  set('lens', st.lens, 'eps'); set('x', st.xw, 'r1m'); set('sec', st.sec); set('cap', st.cap ? String(st.cap) : ''); set('only', st.only);
  set('view', st.view, 'stock'); set('t', st.track.join(',')); set('focus', st.onlyTrack ? '1' : '');
  u.searchParams.delete('zoom');
  history.replaceState(null, '', u);
}

// ---- 점 계산
function mk(id, label, sub, mcap, x, y, yC, jit, r, mine) {
  const xm = XW[st.xw][1], xN = clamp(x / xm, -1, 1), yN = clamp(yC + jit, -1, 1);
  const quad = yC > 0.03 && x < -0.003 ? 'tl' : yC < -0.03 && x > 0.003 ? 'br' : yC >= 0 && x >= 0 ? 'tr' : 'bl';
  return { id, label, sub, mcap, x, y, xN, yN, yC, quad, r, mine, score: Math.min(Math.abs(xN), Math.abs(yC)) + 0.3 * (Math.abs(xN) + Math.abs(yC)) };
}
function stockPoints(ignoreFocus) {
  const L = LENS[st.lens];
  const watch = new Set(Watch.list()), hold = new Set(portfolioTickers()), [w0, w1] = weekRange(), tr = new Set(st.track);
  const out = [];
  for (const r of S) {
    const x = r[st.xw], y = L.y(r);
    if (x == null || y == null) continue;
    const pinned = tr.has(r.t);                  // 궤적을 보고 있는 종목은 필터와 상관없이 항상 표시
    if (!pinned) {
      if (!ignoreFocus && st.onlyTrack && st.track.length) continue;
      if (st.sec && r.sec !== st.sec) continue;
      if (st.cap && (r.mcap || 0) < st.cap) continue;
      if (st.only === 'watch' && !watch.has(r.t)) continue;
      if (st.only === 'hold' && !hold.has(r.t)) continue;
      if (st.only === 'earn' && !(r.c_next && r.c_next >= w0 && r.c_next <= w1)) continue;
    }
    const yC = L.raw ? y : clamp(y / L.max, -1, 1);
    out.push(mk(r.t, r.t, r.ko || r.n || '', r.mcap || 0, x, y, yC, L.jitter ? hash(r.t) * 0.14 : 0, r, watch.has(r.t) || hold.has(r.t)));
  }
  return out;
}
function groupPoints() {
  // 업종 원: 시가총액 가중 평균 (신호는 지도 눈금 끝에서 잘라 평균 — 한 종목이 끌고 가지 않게)
  const L = LENS[st.lens], key = st.view === 'sec' ? 'sec' : 'ind';
  const g = new Map();
  for (const p of stockPoints(true)) {
    if (st.sec && p.r.sec !== st.sec) continue;
    const k = p.r[key];
    if (!k) continue;
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(p);
  }
  const out = [];
  for (const [k, ms] of g) {
    if (ms.length < 3) continue;
    const id = key + ':' + k;
    if (st.onlyTrack && st.track.length && !st.track.includes(id)) continue;
    const w = ms.reduce((a, p) => a + p.mcap, 0) || 1;
    const x = ms.reduce((a, p) => a + p.mcap * p.x, 0) / w;
    const yC = ms.reduce((a, p) => a + p.mcap * p.yC, 0) / w;
    const top = ms.slice().sort((a, b) => b.mcap - a.mcap).slice(0, 3).map(p => p.id).join(' · ');
    out.push(mk(id, key === 'sec' ? secKo(k) : k, `${ms.length}종목 · ${top}`, w, x, yC * (L.raw ? 1 : L.max), yC, 0, null, false));
  }
  return out;
}
const points = () => st.view === 'stock' ? stockPoints(false) : groupPoints();

// ---- 좌표
const iw = () => W - PAD.l - PAD.r, ih = () => H - PAD.t - PAD.b;
const sx = v => PAD.l + (v - st.dom[0]) / (st.dom[1] - st.dom[0]) * iw();
const sy = v => PAD.t + (1 - (v - st.dom[2]) / (st.dom[3] - st.dom[2])) * ih();
const ix = px => st.dom[0] + (px - PAD.l) / iw() * (st.dom[1] - st.dom[0]);
const iy = py => st.dom[2] + (1 - (py - PAD.t) / ih()) * (st.dom[3] - st.dom[2]);
const span = () => st.dom[1] - st.dom[0];
// 업종·세부 업종은 평균이라 가운데에 몰림 → 기본 화면을 원들이 퍼지도록 맞춤 (가로·세로 0은 항상 가운데)
function home() {
  if (st.view === 'stock' || !P.length) return FULL.slice();
  const v = P.map(p => Math.max(Math.abs(p.xN), Math.abs(p.yN))).sort((a, b) => a - b);
  const q = v[Math.min(v.length - 1, Math.floor(v.length * (st.view === 'sec' ? 1 : 0.9)))];   // 세부 업종은 상위 10%의 튀는 값은 가장자리로
  const h = Math.min(FULL[1], Math.max(0.08, q) * 1.35);
  return [-h, h, -h, h];
}
let HOME = FULL.slice();
const zoomed = () => Math.abs(span() - (HOME[1] - HOME[0])) > 1e-6 || Math.abs(st.dom[0] - HOME[0]) > 1e-6 || Math.abs(st.dom[2] - HOME[2]) > 1e-6;
const inDom = p => p.xN >= st.dom[0] && p.xN <= st.dom[1] && p.yN >= st.dom[2] && p.yN <= st.dom[3];

function pick(list, q, n = 8) {
  // 시가총액 100억 달러 이상을 먼저 (작은 종목은 전망치가 몇 배씩 튀는 경우가 많음), 모자라면 나머지로 채움
  const c = list.filter(p => p.quad === q && Math.abs(p.yC) > 0.06 && Math.abs(p.xN) > 0.06).sort((a, b) => b.score - a.score);
  if (st.view !== 'stock') return c.slice(0, n);
  const big = c.filter(p => p.mcap >= 1e10);
  return big.length >= n ? big.slice(0, n) : big.concat(c.filter(p => p.mcap < 1e10)).slice(0, n);
}

// ---- 그리기 (확대·이동 때는 이것만 다시)
function drawChart() {
  drawQueued = false;
  const svg = $('#mx-svg');
  if (!svg) return;
  const L = LENS[st.lens], xm = XW[st.xw][1], up = cssv('--up'), dn = cssv('--dn');
  const [x0, x1, y0, y1] = st.dom, tracking = st.track.length > 0;
  let g = '';
  const tint = { tl: 'color-mix(in srgb, var(--up) 9%, var(--card))', br: 'color-mix(in srgb, var(--dn) 9%, var(--card))' };
  for (const [q, [a, b, c, d]] of [['tl', [-2, 0, 0, 2]], ['br', [0, 2, -2, 0]]]) {
    const ax = Math.max(a, x0), bx = Math.min(b, x1), cy = Math.max(c, y0), dy = Math.min(d, y1);
    if (bx > ax && dy > cy) g += `<rect x="${sx(ax)}" y="${sy(dy)}" width="${sx(bx) - sx(ax)}" height="${sy(cy) - sy(dy)}" fill="${tint[q]}"/>`;
  }
  if (x0 < 0 && x1 > 0) g += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${PAD.t}" y2="${PAD.t + ih()}" stroke="var(--line)" stroke-width="1.2"/>`;
  if (y0 < 0 && y1 > 0) g += `<line x1="${PAD.l}" x2="${PAD.l + iw()}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line)" stroke-width="1.2"/>`;
  for (let i = 0; i <= 4; i++) {
    const v = x0 + (x1 - x0) * i / 4;
    g += `<text x="${sx(v)}" y="${PAD.t + ih() + 16}" font-size="11" text-anchor="middle" fill="var(--faint)">${sgn(v * xm, span() < 0.5 ? 1 : 0)}</text>`;
  }
  g += `<text x="${PAD.l + iw() / 2}" y="${H - 6}" font-size="11.5" text-anchor="middle" fill="var(--muted)">← 최근 ${XW[st.xw][0]} 주가 하락 · 상승 →</text>`;
  g += `<text x="${PAD.l + 6}" y="${PAD.t - 10}" font-size="11.5" fill="var(--muted)">↑ ${esc(L.up)}</text>`;
  g += `<text x="${PAD.l + 6}" y="${PAD.t + ih() + 30}" font-size="11.5" fill="var(--muted)">↓ ${esc(L.dn)}</text>`;
  // 구역 이름 (보이는 영역 안에 충분히 있을 때만)
  const qlab = (q, txt, color) => {
    const box = { tl: [-1.04, 0, 0, 1.04], tr: [0, 1.04, 0, 1.04], bl: [-1.04, 0, -1.04, 0], br: [0, 1.04, -1.04, 0] }[q];
    const ax = Math.max(box[0], x0), bx = Math.min(box[1], x1), cy = Math.max(box[2], y0), dy = Math.min(box[3], y1);
    if (sx(bx) - sx(ax) < 160 || sy(cy) - sy(dy) < 50) return '';
    const left = q === 'tl' || q === 'bl', top = q === 'tl' || q === 'tr';
    return `<text x="${left ? sx(ax) + 12 : sx(bx) - 12}" y="${top ? sy(dy) + 22 : sy(cy) - 12}" font-size="${W < 600 ? 12 : 14}" font-weight="800" text-anchor="${left ? 'start' : 'end'}" fill="${color}">${esc(txt)}</text>`;
  };
  g += qlab('tl', L.tl, up) + qlab('br', L.br, dn) + qlab('tr', '둘 다 좋음', 'var(--faint)') + qlab('bl', '둘 다 나쁨', 'var(--faint)');
  // 점
  const vis = P.filter(inDom).sort((a, b) => b.mcap - a.mcap);
  const maxM = Math.max(...P.map(p => p.mcap), 1);
  const base = st.view !== 'stock' ? (st.view === 'sec' ? 34 : 24) : P.length > 400 ? 18 : P.length > 150 ? 24 : 32;
  const zk = Math.min(1.8, Math.pow((FULL[1] - FULL[0]) / span(), 0.22));
  const hot = new Set([...pick(vis, 'tl'), ...pick(vis, 'br')].map(p => p.id));
  const tset = new Set(st.track);
  let dots = '', labs = '';
  for (const p of vis) {
    const rad = (3 + Math.sqrt(p.mcap / maxM) * base) * zk, cx = sx(p.xN), cy = sy(p.yN);
    const col = p.quad === 'tl' ? up : p.quad === 'br' ? dn : 'var(--faint)';
    const tracked = tset.has(p.id), fade = tracking && !tracked;
    const op = tracked ? 0.38 : (p.quad === 'tl' || p.quad === 'br' ? 0.72 : 0.32) * (fade ? 0.22 : 1);
    const tc = tracked ? TRACK_COL[st.track.indexOf(p.id) % TRACK_COL.length] : null;
    const ring = tracked ? `stroke="${tc}" stroke-width="2.5"` : p.mine ? `stroke="var(--ink)" stroke-width="1.5"` : `stroke="${col}" stroke-opacity="${fade ? 0.18 : 0.9}" stroke-width="1"`;
    dots += `<circle class="dot" data-id="${esc(p.id)}" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad.toFixed(1)}" fill="${col}" fill-opacity="${op}" ${ring}/>`;
    p._cx = cx; p._cy = cy; p._r = rad;
  }
  const labN = tracking ? 0 : Math.min(90, Math.round((W < 600 ? 10 : st.view === 'ind' ? 12 : 22) * Math.pow((HOME[1] - HOME[0]) / span(), 0.8)));
  const showHot = st.view === 'stock' || zoomed();        // 세부 업종은 이름이 길어 확대했을 때만 강조 이름을 모두 표시
  const lab = vis.filter((p, i) => st.view === 'sec' || i < labN || (!tracking && showHot && (hot.has(p.id) || p.mine)) || tset.has(p.id));
  for (const p of lab) {
    const strong = hot.has(p.id) || tset.has(p.id) || st.view === 'sec';
    const name = st.view !== 'stock' ? p.label : (p.r.ko && span() < 1 && p._r >= 14 && p.r.ko.length <= 6 ? p.r.ko : p.id);
    const inside = st.view === 'sec' && p._r > 26;
    labs += `<text x="${(inside ? p._cx : p._cx + p._r + 3).toFixed(1)}" y="${(p._cy + 4).toFixed(1)}" text-anchor="${inside ? 'middle' : 'start'}" font-size="${strong ? 12.5 : 11}" font-weight="${strong ? 800 : 600}" fill="var(--ink)" paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round" pointer-events="none">${esc(name)}</text>`;
  }
  const trails = st.track.map((id, i) => trailLayer(id, TRACK_COL[i % TRACK_COL.length])).join('');
  svg.innerHTML = g + dots + trails + labs;
  $('#mx-count').textContent = `${vis.length.toLocaleString()}개 ${st.view === 'stock' ? '종목' : VIEWS[st.view]}${zoomed() ? ' (확대)' : ''} · ${U.asof} 기준`;
  const zb = $('#mx-reset'); if (zb) zb.style.visibility = zoomed() ? 'visible' : 'hidden';
  svg.style.touchAction = zoomed() ? 'none' : 'pan-y';   // 확대했을 때만 한 손가락으로 지도 이동 (아니면 페이지 스크롤)
}
const queueDraw = () => { if (!drawQueued) { drawQueued = true; requestAnimationFrame(drawChart); } };

// ---- 궤적: 지도와 같은 기준(선택한 기간의 주가 × 그 시점의 신호)으로 과거 위치를 이어 그림. 끝점 = 지금 점
function trailPts(id) {
  const L = LENS[st.lens];
  if (!L.trail) return null;
  if (isGroup(id)) { const k = id.startsWith('sec:') ? 'sec' : 'ind'; return GT && GT[k] && GT[k][groupName(id)] ? GT[k][groupName(id)][L.trail] : null; }
  return st.trail[id] ? st.trail[id][L.trail] : null;
}
function trailLayer(id, color) {
  const L = LENS[st.lens], pts = trailPts(id);
  if (!pts || !pts.length) return '';
  const xm = XW[st.xw][1], xi = XI[st.xw], cur = P.find(p => p.id === id);
  const jit = L.jitter && !isGroup(id) ? hash(id) * 0.14 : 0;
  const C = pts.filter(q => q[xi] != null && q[5] != null).map(q => ({ d: q[0], xN: clamp(q[xi] / xm, -1, 1), yN: clamp((L.raw ? q[5] : q[5] / L.max) + jit, -1, 1) }));
  if (cur) {                                   // 마지막 날짜가 최근 거래일이면 지금 점으로 바꾸고, 분기 자료면 지금 점을 덧붙임
    const now = { d: U.asof, xN: cur.xN, yN: cur.yN };
    if (C.length && C[C.length - 1].d >= U.asof) C[C.length - 1] = now; else C.push(now);
  }
  if (C.length < 2) return '';
  const XY = C.map(c => [sx(c.xN), sy(c.yN)]), n = XY.length;
  const op = i => 0.32 + 0.68 * Math.pow(i / (n - 1), 1.1);      // 과거는 연하게, 지금에 가까울수록 진하게
  let halo = '', g = '';
  for (let i = 1; i < n; i++) {
    const [ax, ay] = XY[i - 1], [bx, by] = XY[i];
    const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
    const r0 = 6.5, r1 = i === n - 1 ? (cur && cur._r ? cur._r : 8) + 5 : 7.5;   // 점에 붙지 않게 양 끝을 띄움
    if (len <= r0 + r1 + 4) continue;
    const ux = dx / len, uy = dy / len;
    const s0x = ax + ux * r0, s0y = ay + uy * r0, ex = bx - ux * r1, ey = by - uy * r1;
    const o = op(i).toFixed(2), w = (1.4 + 1.2 * i / (n - 1)).toFixed(2);
    const ah = 6.5, aw = 3.4, hx = ex - ux * ah, hy = ey - uy * ah;
    const head = `${(hx - uy * aw).toFixed(1)},${(hy + ux * aw).toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)} ${(hx + uy * aw).toFixed(1)},${(hy - ux * aw).toFixed(1)}`;
    halo += `<line x1="${s0x.toFixed(1)}" y1="${s0y.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="var(--card)" stroke-width="${(+w + 3).toFixed(1)}" stroke-linecap="round" stroke-opacity="0.9"/>`;
    halo += `<polyline points="${head}" fill="none" stroke="var(--card)" stroke-width="${(+w + 3).toFixed(1)}" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.9"/>`;
    g += `<line x1="${s0x.toFixed(1)}" y1="${s0y.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${color}" stroke-opacity="${o}" stroke-width="${w}" stroke-linecap="round"/>`;
    g += `<polyline points="${head}" fill="none" stroke="${color}" stroke-opacity="${o}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  XY.forEach(([x, y], i) => {
    if (i === n - 1) return;                  // 끝점은 지도 위 실제 점이 그 자리
    const o = op(i);
    g += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${color}" fill-opacity="${o.toFixed(2)}" stroke="var(--card)" stroke-width="2"/>`;
    g += `<text x="${(x + 8).toFixed(1)}" y="${(y - 7).toFixed(1)}" font-size="11" font-weight="600" fill="${color}" fill-opacity="${Math.max(0.6, o).toFixed(2)}" paint-order="stroke" stroke="var(--card)" stroke-width="3.5" stroke-linejoin="round">${esc(C[i].d.slice(5).replace('-', '/'))}</text>`;
  });
  return `<g pointer-events="none">${halo}${g}</g>`;
}

// ---- 화면 조각
function controls() {
  const secs = [...new Set(S.map(r => r.sec).filter(Boolean))].sort((a, b) => secKo(a).localeCompare(secKo(b), 'ko'));
  return `<div class="mx-ctl">
    <div class="mx-seg" role="tablist" aria-label="세로축 신호">${Object.entries(LENS).map(([k, l]) => `<button role="tab" aria-selected="${k === st.lens}" class="${k === st.lens ? 'on' : ''}" data-lens="${k}">${l.name}</button>`).join('')}</div>
    <div class="mx-seg" role="tablist" aria-label="가로축 주가 기간">${Object.entries(XW).map(([k, [l]]) => `<button role="tab" aria-selected="${k === st.xw}" class="${k === st.xw ? 'on' : ''}" data-xw="${k}">${l}</button>`).join('')}</div>
    <div class="mx-seg" role="tablist" aria-label="보기 단위">${Object.entries(VIEWS).map(([k, l]) => `<button role="tab" aria-selected="${k === st.view}" class="${k === st.view ? 'on' : ''}" data-view="${k}">${l}</button>`).join('')}</div>
  </div>
  <details class="mx-more" ${window.innerWidth >= 700 || st.track.length ? 'open' : ''}><summary>찾기 · 필터</summary><div class="mx-ctl">
    <div class="mx-find"><input type="search" class="f" id="mx-q" placeholder="${st.view === 'stock' ? '종목 찾아 궤적 보기 (최대 5개)' : '업종 찾기'}" autocomplete="off" aria-label="지도에서 찾기"><div class="mx-sugg" id="mx-sugg"></div></div>
    <label class="s13 mut">업종 <select class="f" id="f-sec"><option value="">전체</option>${secs.map(s => `<option value="${esc(s)}" ${s === st.sec ? 'selected' : ''}>${esc(secKo(s))}</option>`).join('')}</select></label>
    <label class="s13 mut">시가총액 <select class="f" id="f-cap">${[[0, '전체'], [1e10, '100억 달러 이상'], [1e11, '1,000억 달러 이상']].map(([v, l]) => `<option value="${v}" ${v === st.cap ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    <div class="mx-seg" aria-label="보기 범위">${[['', '전체'], ['watch', `관심 ${Watch.list().length}`], ['hold', `보유 ${portfolioTickers().length}`], ['earn', '이번 주 실적']].map(([k, l]) => `<button class="${k === st.only ? 'on' : ''}" data-only="${k}">${l}</button>`).join('')}</div>
  </div></details>
  ${st.track.length ? `<div class="mx-ctl"><span class="s13 mut">궤적</span>${st.track.map((id, i) => `<span class="mx-chip"><i style="background:${TRACK_COL[i % TRACK_COL.length]}"></i><b>${esc(labelOf(id))}</b><button data-untrack="${esc(id)}" aria-label="${esc(labelOf(id))} 빼기">×</button></span>`).join('')}
    <label class="s13" style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="mx-focus" ${st.onlyTrack ? 'checked' : ''}> 이것만 보기</label>
    <button class="btn" id="mx-clear" style="min-height:30px;padding:2px 10px">모두 지우기</button></div>` : ''}`;
}

function side() {
  const L = LENS[st.lens];
  const visible = P.filter(inDom);
  if (st.track.length) {
    return st.track.map((id, i) => {
      const p = P.find(q => q.id === id), color = TRACK_COL[i % TRACK_COL.length], pts = trailPts(id);
      const r = isGroup(id) ? null : S.find(x => x.t === id);
      const note = !L.trail ? '내부자 렌즈는 궤적이 없어요. 종목 화면의 거래 목록을 보세요.'
        : pts && pts.length ? `${esc(pts[0][0])}부터 지금까지 지나온 길 · 연한 점이 과거, 진한 쪽이 최근`
        : isGroup(id) ? (GT ? '이 묶음은 이 렌즈의 궤적 자료가 없어요.' : '궤적 불러오는 중…') : st.trail[id] ? '이 종목은 이 렌즈의 궤적 자료가 없어요.' : '궤적 불러오는 중…';
      return `<div class="card" style="box-shadow:inset 3px 0 0 ${color}"><div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap"><h3 style="font-size:17px">${esc(labelOf(id))}</h3><span class="mut s13">${esc(r ? (r.ko || r.n) : p ? p.sub : '')}</span></div>
        ${p ? `<div class="kv"><div><span>최근 ${XW[st.xw][0]} 주가</span><b>${pctS(p.x)}</b></div><div><span>${esc(L.name)}</span><b>${esc(L.fy(p.y, p.r))}</b></div><div><span>시가총액</span><b>${fmtUsd(p.mcap)}</b></div>${r ? `<div><span>다음 실적</span><b>${esc(r.c_next || '-')}</b></div>` : ''}</div>` : `<div class="mut s13">지금 렌즈·기간에 값이 없어요</div>`}
        ${r && r.s1 ? `<p class="s13" style="margin:0">${esc(r.s1)}</p>` : ''}
        <div class="small mut">${note}</div>
        ${r ? `<div style="display:flex;gap:6px;align-items:center"><a class="btn dark" href="${stockUrl(r.t)}" style="flex:1;text-align:center;text-decoration:none">종목 화면 →</a>${starBtn(r.t)}</div>` : ''}</div>`;
    }).join('');
  }
  const row = p => `<a data-pick="${esc(p.id)}" class="${st.view === 'stock' ? '' : 'g'}"><b>${esc(st.view === 'stock' ? p.id : p.label)}</b><small>${esc(st.view === 'stock' ? p.sub : '')}</small><span class="v">${sgn(p.x)} · ${esc(L.fy(p.y, p.r))}</span></a>`;
  const tl = pick(visible, 'tl'), br = pick(visible, 'br'), where = zoomed() ? '확대한 영역 · ' : '';
  return `<div class="card"><h3>어떻게 읽나요</h3><p class="s13 mut" style="margin:0">${esc(L.desc)}</p><p class="small faint" style="margin:0">휠·두 손가락으로 확대, 끌어서 이동, 두 번 누르면 전체 보기. 점을 누르면 궤적(지나온 길)을, Shift를 누른 채 누르면 여러 개를 함께 그려요.</p></div>
    <div class="card"><h3 style="color:var(--up)">${esc(where + L.tl)}</h3><div class="mx-list">${tl.map(row).join('') || '<span class="mut s13">해당하는 곳이 없어요</span>'}</div></div>
    <div class="card"><h3 style="color:var(--dn)">${esc(where + L.br)}</h3><div class="mx-list">${br.map(row).join('') || '<span class="mut s13">해당하는 곳이 없어요</span>'}</div></div>`;
}
const queueSide = () => { clearTimeout(sideTimer); sideTimer = setTimeout(() => { $('#mx-side').innerHTML = side(); bindSide(); }, 220); };

// ---- 전체 다시 그리기 (렌즈·필터·궤적 목록이 바뀔 때)
function render(keepDom) {
  P = points();
  const prevHome = HOME;
  HOME = home();
  if (!keepDom && st.view !== 'stock') st.dom = HOME.slice();
  else if (st.view === 'stock' && prevHome !== HOME && span() > FULL[1] - FULL[0] - 1e-6) st.dom = FULL.slice();
  $('#mx-ctl').innerHTML = controls();
  const box = $('#mx-chart');
  W = Math.max(320, box.clientWidth);
  H = W < 600 ? Math.round(W * 1.05) : Math.min(680, Math.round(W * 0.72));
  const L = LENS[st.lens];
  box.innerHTML = `<div class="mx-bar"><button class="btn" id="mx-zin" aria-label="확대">＋</button><button class="btn" id="mx-zout" aria-label="축소">－</button><button class="btn" id="mx-reset">전체 보기</button></div>
    <svg id="mx-svg" viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="어긋남 지도: 가로 최근 ${XW[st.xw][0]} 주가, 세로 ${esc(L.name)}"></svg><div class="mx-tip" id="mx-tip"></div>`;
  drawChart();
  $('#mx-side').innerHTML = side();
  bindCtl(); bindChart(); bindSide();
  sync();
}

async function ensureTrails() {
  const need = st.track.filter(id => !isGroup(id) && !st.trail[id]);
  if (st.track.some(isGroup) && !GT) { try { GT = await getJSON('free/sector_trails.json'); } catch (e) { GT = { sec: {}, ind: {} }; } }
  await Promise.all(need.map(async t => { try { st.trail[t] = (await Data.stock(t)).trail || {}; } catch (e) { st.trail[t] = {}; } }));
  render(true);
}
function track(id, add) {
  if (add) { if (!st.track.includes(id)) st.track = [...st.track, id].slice(-5); }
  else st.track = st.track.length === 1 && st.track[0] === id ? [] : [id];
  render(true); ensureTrails();
}

// ---- 이벤트
function bindCtl() {
  document.querySelectorAll('[data-lens]').forEach(b => b.onclick = () => { st.lens = b.dataset.lens; render(); });
  document.querySelectorAll('[data-xw]').forEach(b => b.onclick = () => { st.xw = b.dataset.xw; render(); });
  document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => { if (st.view !== b.dataset.view) { st.view = b.dataset.view; st.track = []; st.onlyTrack = false; st.dom = FULL.slice(); } render(); });
  document.querySelectorAll('[data-only]').forEach(b => b.onclick = () => { st.only = b.dataset.only; render(); });
  document.querySelectorAll('[data-untrack]').forEach(b => b.onclick = () => { st.track = st.track.filter(x => x !== b.dataset.untrack); render(true); });
  $('#f-sec').onchange = e => { st.sec = e.target.value; render(); };
  $('#f-cap').onchange = e => { st.cap = +e.target.value; render(); };
  const fc = $('#mx-focus'); if (fc) fc.onchange = e => { st.onlyTrack = e.target.checked; render(); };
  const cl = $('#mx-clear'); if (cl) cl.onclick = () => { st.track = []; st.onlyTrack = false; render(); };
  // 지도 안 검색: 종목(또는 업종)을 찾아 궤적 목록에 추가
  const q = $('#mx-q'), box = $('#mx-sugg');
  let list = [], sel = -1;
  const show = () => {
    const v = q.value.trim(), V = v.toUpperCase();
    if (!v) { box.style.display = 'none'; return; }
    if (st.view === 'stock') {
      const a = S.filter(r => r.t === V), b = S.filter(r => r.t !== V && r.t.startsWith(V)), c = S.filter(r => !r.t.startsWith(V) && ((r.n || '').toUpperCase().includes(V) || (r.ko || '').includes(v)));
      list = [...a, ...b.sort((x, y) => (y.mcap || 0) - (x.mcap || 0)), ...c.sort((x, y) => (y.mcap || 0) - (x.mcap || 0))].slice(0, 8).map(r => ({ id: r.t, l: r.t, s: r.ko || r.n || '' }));
    } else {
      list = P.filter(p => p.label.toUpperCase().includes(V) || p.id.toUpperCase().includes(V)).slice(0, 8).map(p => ({ id: p.id, l: p.label, s: p.sub }));
    }
    sel = -1;
    box.innerHTML = list.map((x, i) => `<a data-i="${i}"><b>${esc(x.l)}</b><span>${esc(x.s)}</span></a>`).join('') || '<a><span>찾는 결과가 없어요</span></a>';
    box.style.display = 'block';
    box.querySelectorAll('a[data-i]').forEach(a => a.onmousedown = e => { e.preventDefault(); choose(list[+a.dataset.i]); });
  };
  const choose = x => { if (!x) return; q.value = ''; box.style.display = 'none'; track(x.id, true); };
  q.oninput = show;
  q.onkeydown = e => {
    const as = box.querySelectorAll('a[data-i]');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); sel = clamp(sel + (e.key === 'ArrowDown' ? 1 : -1), 0, as.length - 1); as.forEach((a, i) => a.classList.toggle('sel', i === sel)); }
    else if (e.key === 'Enter') choose(list[sel >= 0 ? sel : 0]);
    else if (e.key === 'Escape') box.style.display = 'none';
  };
  q.onblur = () => setTimeout(() => { box.style.display = 'none'; }, 150);
}

function fit([x0, x1, y0, y1]) {
  const w = x1 - x0;
  if (w >= FULL[1] - FULL[0] - 1e-9) return FULL.slice();
  const sh = (a, b, lo, hi) => a < lo ? [lo, lo + (b - a)] : b > hi ? [hi - (b - a), hi] : [a, b];
  [x0, x1] = sh(x0, x1, FULL[0], FULL[1]); [y0, y1] = sh(y0, y1, FULL[2], FULL[3]);
  return [x0, x1, y0, y1];
}
function zoomAt(cx, cy, f) {
  // 화면 좌표 (cx, cy)를 중심으로 확대(f<1)·축소(f>1)
  const u = ix(cx), v = iy(cy);
  const w = clamp(span() * f, 0.04, FULL[1] - FULL[0]), k = w / span();
  let [x0, , y0] = st.dom;
  x0 = u - (u - x0) * k; y0 = v - (v - y0) * k;
  st.dom = fit([x0, x0 + w, y0, y0 + w]);
  queueDraw(); queueSide();
}

function bindChart() {
  const svg = $('#mx-svg'), tip = $('#mx-tip'), chart = $('#mx-chart'), L = LENS[st.lens];
  const local = e => { const r = svg.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const [x, y] = local(e);
    zoomAt(x, y, Math.exp(clamp(e.deltaY, -120, 120) * 0.0022));
  }, { passive: false });
  // 끌어서 이동 · 두 손가락 확대 (포인터 이벤트 하나로 마우스·터치 모두)
  const ptrs = new Map();
  let drag = null, moved = false, pinch = null;
  svg.addEventListener('pointerdown', e => {
    ptrs.set(e.pointerId, local(e));
    if (ptrs.size === 1) { moved = false; drag = { p: local(e), dom: st.dom.slice() }; }
    if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), dom: st.dom.slice(), c: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] }; drag = null; moved = true; }
    try { svg.setPointerCapture(e.pointerId); } catch (_) { }
  });
  svg.addEventListener('pointermove', e => {
    if (!ptrs.has(e.pointerId)) {
      const id = e.target.dataset && e.target.dataset.id, p = id && P.find(q => q.id === id);   // 마우스 올림 설명
      if (!p) { tip.style.display = 'none'; return; }
      const rc = chart.getBoundingClientRect();
      tip.innerHTML = `<b>${esc(st.view === 'stock' ? p.id : p.label)}</b> ${esc(st.view === 'stock' ? p.sub : '')}<br>${XW[st.xw][0]} 주가 ${sgn(p.x, 1)} · ${esc(L.fy(p.y, p.r))}<br>시가총액 ${fmtUsd(p.mcap)}${st.view !== 'stock' ? '<br>' + esc(p.sub) : ''}`;
      tip.style.display = 'block';
      const x = e.clientX - rc.left + 14, y = e.clientY - rc.top + 14;
      tip.style.left = Math.min(x, rc.width - tip.offsetWidth - 8) + 'px'; tip.style.top = Math.min(y, rc.height - tip.offsetHeight - 8) + 'px';
      return;
    }
    ptrs.set(e.pointerId, local(e));
    if (pinch && ptrs.size === 2) {
      const [a, b] = [...ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      st.dom = pinch.dom.slice();
      zoomAt(pinch.c[0], pinch.c[1], pinch.d / Math.max(10, d));
      return;
    }
    if (drag) {
      const [x, y] = local(e), dx = x - drag.p[0], dy = y - drag.p[1];
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      if (!moved || !zoomed()) return;
      const [x0, x1, y0, y1] = drag.dom, kx = (x1 - x0) / iw(), ky = (y1 - y0) / ih();
      st.dom = fit([x0 - dx * kx, x1 - dx * kx, y0 + dy * ky, y1 + dy * ky]);
      tip.style.display = 'none';
      queueDraw(); queueSide();
    }
  });
  const end = e => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.delete(e.pointerId);
    if (ptrs.size < 2) pinch = null;
    if (ptrs.size === 0) {
      drag = null;
      if (!moved && e.type === 'pointerup') {
        // 포인터를 잡고 있으면 e.target이 svg라서, 손을 뗀 자리의 점을 찾음
        const el = document.elementFromPoint(e.clientX, e.clientY), id = el && el.dataset && el.dataset.id;
        if (id) track(id, e.shiftKey || e.metaKey || e.ctrlKey);
      }
    }
  };
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
  svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
  svg.addEventListener('dblclick', () => { st.dom = HOME.slice(); queueDraw(); queueSide(); });
  const c = () => [PAD.l + iw() / 2, PAD.t + ih() / 2];
  $('#mx-zin').onclick = () => zoomAt(...c(), 0.6);
  $('#mx-zout').onclick = () => zoomAt(...c(), 1 / 0.6);
  $('#mx-reset').onclick = () => { st.dom = HOME.slice(); queueDraw(); queueSide(); };
}
function bindSide() {
  document.querySelectorAll('[data-pick]').forEach(a => a.onclick = e => { e.preventDefault(); track(a.dataset.pick, false); });
}

(async () => {
  try { U = await Data.universe(); }
  catch (e) { $('#app').innerHTML = `<div class="loading">불러오지 못했습니다 (${esc(e.message)})</div>`; return; }
  S = U.rows.filter(r => r.k === 'stock');
  $('#app').innerHTML = `<div class="hero"><h1>어긋남 지도</h1><p>주가와 신호가 반대로 간 종목을 찾는 지도 · 가로 = 주가, 세로 = 고른 신호, 점 크기 = 시가총액 · <span id="mx-count"></span></p></div>
    <div class="card" id="mx-ctl" style="gap:10px"></div>
    <div class="mx-wrap"><div class="mx-chart" id="mx-chart"></div><div class="mx-side" id="mx-side"></div></div>
    <div class="small faint">정보 제공용이며 투자 권유가 아닙니다 · 가로축 범위 밖의 종목은 가장자리에 붙여 그립니다 · 업종 원은 시가총액 가중 평균 · 출처: SEC EDGAR(재무·내부자·13F), FINRA(공매도), yfinance(가격·컨센서스)</div>`;
  render();
  if (st.track.length) ensureTrails();
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => render(true), 150); });
  document.addEventListener('watch-change', () => render(true));
  footer();
})();
