// 어긋남 지도 — 가로 = 주가(기간 선택), 세로 = 신호(렌즈), 점 크기 = 시가총액
// 신호와 주가가 반대로 간 왼쪽 위·오른쪽 아래가 핵심. 구역을 누르면 확대, 종목을 누르면 지도 위 이동 경로
header('지도');
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const XW = { r1w: ['1주', 0.12], r1m: ['1개월', 0.3], r3m: ['3개월', 0.5], r6m: ['6개월', 0.7] };
const money = v => { const a = Math.abs(v); return a >= 1e8 ? '$' + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + '억' : a >= 1e4 ? '$' + Math.round(a / 1e4) + '만' : '$' + Math.round(a); };
const sgn = (v, d = 0) => (v > 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
const LENS = {
  eps: {
    name: 'EPS 전망', max: 0.3, y: r => (r.c_chg90 != null && (r.c_n || 0) >= 3) ? r.c_chg90 : null, v: r => '전망 ' + sgn(r.c_chg90, Math.abs(r.c_chg90) < 0.1 ? 1 : 0),
    up: '내년 EPS 전망 상향', dn: '전망 하향', tl: '전망은 오르는데 주가는 빠짐', br: '주가는 오르는데 전망은 꺾임',
    desc: '세로 = 애널리스트들의 내년 EPS(주당순이익) 전망이 90일 전보다 얼마나 바뀌었나. 왼쪽 위는 이익 전망이 좋아지는데 주가가 빠진 종목입니다.',
    trail: 'eps', tx: '90일 전 대비 주가', ty: '90일 전 대비 EPS 전망', tfmt: v => sgn(v, 1),
  },
  rev: {
    name: '매출 가속', max: 0.3, y: r => (r.rev_qg != null && r.rev_g != null) ? r.rev_qg - r.rev_g : null,
    v: r => '가속 ' + ((r.rev_qg - r.rev_g) > 0 ? '+' : '') + ((r.rev_qg - r.rev_g) * 100).toFixed(1) + '%p',
    up: '매출 성장 가속', dn: '매출 성장 둔화', tl: '매출 성장은 빨라지는데 주가는 빠짐', br: '주가는 오르는데 매출 성장은 둔화',
    desc: '세로 = 최근 분기 매출 성장률(1년 전 같은 분기 대비)에서 최근 4개 분기 합계 성장률을 뺀 값. 플러스면 성장이 빨라지는 중입니다. SEC 재무제표 기준.',
    trail: 'rev', tx: '시작 분기 대비 주가', ty: '분기 매출 성장 가속', tfmt: v => (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%p',
  },
  guru: {
    name: '유명 투자자', max: 5, jitter: true, y: r => r.g13_chg ?? null, v: r => '투자자 ' + (r.g13_chg > 0 ? '+' : '') + r.g13_chg + '곳',
    up: '유명 투자자 순매수', dn: '순매도', tl: '유명 투자자는 사는데 주가는 빠짐', br: '주가는 오르는데 유명 투자자는 팖',
    desc: '세로 = 유명 투자자 36곳 중 이번 분기 새로 사거나 늘린 곳 − 팔거나 줄인 곳 (13F). 13F는 분기 말 기준이라 최대 4개월 반 늦은 정보예요.',
    trail: 'guru', tx: '시작 분기 대비 주가', ty: '보유한 유명 투자자 수 변화', tfmt: v => (v > 0 ? '+' : '') + v + '곳',
  },
  insider: {
    name: '내부자', max: 1, raw: true,
    y: r => { const n = (r.ib || 0) - (r.is || 0); return n ? Math.sign(n) * Math.max(0.05, Math.min(1, (Math.log10(Math.abs(n)) - 4) / 4.5)) : null; },
    v: r => { const n = (r.ib || 0) - (r.is || 0); return (n > 0 ? '순매수 ' : '순매도 ') + money(n); },
    up: '내부자 순매수 (금액, 로그)', dn: '순매도', tl: '내부자는 사는데 주가는 빠짐', br: '주가는 오르는데 내부자는 팖',
    desc: '세로 = 최근 90일 임원·이사의 장내 매수 − 매도 금액 (Form 4, 로그 눈금). 매도는 세금·계획 매도가 많아 매수 쪽 신호가 더 의미 있어요.',
    trail: null,
  },
  short: {
    name: '공매도', max: 0.12, y: r => r.sv_chg != null ? -r.sv_chg : null,
    v: r => '공매도 ' + (r.sv_chg > 0 ? '+' : '') + (r.sv_chg * 100).toFixed(1) + '%p',
    up: '공매도 감소', dn: '공매도 증가', tl: '공매도는 줄었는데 주가는 빠짐', br: '주가는 오르는데 공매도는 늘어남',
    desc: '세로 = 공매도 거래 비중(최근 20거래일)이 직전 20거래일보다 얼마나 줄었나. 오른쪽 아래는 주가가 오르는 동안 하락에 거는 거래가 늘어난 종목입니다.',
    trail: 'short', tx: '90일 전 대비 주가', ty: '90일 전 대비 공매도 비중 감소', tfmt: v => (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%p',
  },
};
const ZOOM = { tl: [-1, 0, 0, 1], tr: [0, 1, 0, 1], bl: [-1, 0, -1, 0], br: [0, 1, -1, 0] };
const st = {
  lens: LENS[qs('lens')] ? qs('lens') : 'eps', xw: XW[qs('x')] ? qs('x') : 'r1m', sec: qs('sec') || '', cap: +(qs('cap') || 0),
  only: qs('only') || '', zoom: ZOOM[qs('zoom')] ? qs('zoom') : null, sel: qs('t') || null, trail: null,
};
let U, S, W = 900, H = 640;

const nyToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const addDays = (s, n) => { const d = new Date(s + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
function weekRange() { const t = nyToday(), dw = new Date(t + 'T12:00:00Z').getUTCDay(), m = addDays(t, -((dw + 6) % 7)); return [m, addDays(m, 6)]; }
const hash = s => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 997; return h / 997 - 0.5; };

function sync() {
  const u = new URL(location.href);
  const set = (k, v, d) => v && v !== d ? u.searchParams.set(k, v) : u.searchParams.delete(k);
  set('lens', st.lens, 'eps'); set('x', st.xw, 'r1m'); set('sec', st.sec); set('cap', st.cap ? String(st.cap) : ''); set('only', st.only); set('zoom', st.zoom); set('t', st.sel);
  history.replaceState(null, '', u);
}

function points() {
  const L = LENS[st.lens], xm = XW[st.xw][1];
  const watch = new Set(Watch.list()), hold = new Set(portfolioTickers()), [w0, w1] = weekRange();
  const out = [];
  for (const r of S) {
    const x = r[st.xw], y = L.y(r);
    if (x == null || y == null) continue;
    if (st.sec && r.sec !== st.sec) continue;
    if (st.cap && (r.mcap || 0) < st.cap) continue;
    if (st.only === 'watch' && !watch.has(r.t)) continue;
    if (st.only === 'hold' && !hold.has(r.t)) continue;
    if (st.only === 'earn' && !(r.c_next && r.c_next >= w0 && r.c_next <= w1)) continue;
    const xN = Math.max(-1, Math.min(1, x / xm));
    const yC = L.raw ? y : Math.max(-1, Math.min(1, y / L.max));
    // 유명 투자자 수처럼 정수 값은 점이 한 줄에 겹치므로 그릴 때만 살짝 흩뜨림 (구역 판정은 원래 값으로)
    const yN = L.jitter ? Math.max(-1, Math.min(1, yC + hash(r.t) * 0.14)) : yC;
    const quad = yC > 0.03 && x < -0.003 ? 'tl' : yC < -0.03 && x > 0.003 ? 'br' : yC >= 0 && x >= 0 ? 'tr' : 'bl';
    out.push({ r, x, xN, yN, yC, quad, mine: watch.has(r.t) || hold.has(r.t), score: Math.min(Math.abs(xN), Math.abs(yC)) + 0.3 * (Math.abs(xN) + Math.abs(yC)) });
  }
  return out;
}

function controls() {
  const secs = [...new Set(S.map(r => r.sec).filter(Boolean))].sort((a, b) => secKo(a).localeCompare(secKo(b), 'ko'));
  return `<div class="mx-ctl">
    <div class="mx-seg" role="tablist" aria-label="세로축 신호">${Object.entries(LENS).map(([k, l]) => `<button role="tab" aria-selected="${k === st.lens}" class="${k === st.lens ? 'on' : ''}" data-lens="${k}">${l.name}</button>`).join('')}</div>
    <div class="mx-seg" role="tablist" aria-label="가로축 주가 기간">${Object.entries(XW).map(([k, [l]]) => `<button role="tab" aria-selected="${k === st.xw}" class="${k === st.xw ? 'on' : ''}" data-xw="${k}">${l}</button>`).join('')}</div>
  </div>
  <div class="mx-ctl">
    <label class="s13 mut">업종 <select class="f" id="f-sec"><option value="">전체</option>${secs.map(s => `<option value="${esc(s)}" ${s === st.sec ? 'selected' : ''}>${esc(secKo(s))}</option>`).join('')}</select></label>
    <label class="s13 mut">시가총액 <select class="f" id="f-cap">${[[0, '전체'], [1e10, '100억 달러 이상'], [1e11, '1,000억 달러 이상']].map(([v, l]) => `<option value="${v}" ${v === st.cap ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    <div class="mx-seg" aria-label="보기 범위">${[['', '전체'], ['watch', `관심 종목 ${Watch.list().length}`], ['hold', `보유 종목 ${portfolioTickers().length}`], ['earn', '이번 주 실적 발표']].map(([k, l]) => `<button class="${k === st.only ? 'on' : ''}" data-only="${k}">${l}</button>`).join('')}</div>
  </div>`;
}

function draw(P, trail) {
  const L = LENS[st.lens], xm = XW[st.xw][1];
  const [x0, x1, y0, y1] = st.zoom ? ZOOM[st.zoom] : [-1, 1, -1, 1];
  const pl = 54, pr = 18, pt = 44, pb = 40, iw = W - pl - pr, ih = H - pt - pb;
  const sx = v => pl + (v - x0) / (x1 - x0) * iw, sy = v => pt + (1 - (v - y0) / (y1 - y0)) * ih;
  const up = cssv('--up'), dn = cssv('--dn');
  const tint = { tl: 'color-mix(in srgb, var(--up) 9%, var(--card))', br: 'color-mix(in srgb, var(--dn) 9%, var(--card))', tr: 'var(--card)', bl: 'var(--card)' };
  let g = '';
  // 사분면 배경 (누르면 확대)
  for (const [q, [a, b, c, d]] of Object.entries(ZOOM)) {
    const ax = Math.max(a, x0), bx = Math.min(b, x1), cy = Math.max(c, y0), dy = Math.min(d, y1);
    if (bx <= ax || dy <= cy) continue;
    g += `<rect class="${st.zoom ? '' : 'qbg'}" data-q="${q}" x="${sx(ax)}" y="${sy(dy)}" width="${sx(bx) - sx(ax)}" height="${sy(cy) - sy(dy)}" fill="${tint[q]}"><title>${st.zoom ? '' : '눌러서 확대: ' + (q === 'tl' ? L.tl : q === 'br' ? L.br : q === 'tr' ? '둘 다 좋음' : '둘 다 나쁨')}</title></rect>`;
  }
  if (x0 < 0 && x1 > 0) g += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${pt}" y2="${pt + ih}" stroke="var(--line)" stroke-width="1.2"/>`;
  if (y0 < 0 && y1 > 0) g += `<line x1="${pl}" x2="${pl + iw}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line)" stroke-width="1.2"/>`;
  // 눈금
  for (let i = 0; i <= 4; i++) {
    const v = x0 + (x1 - x0) * i / 4;
    g += `<text x="${sx(v)}" y="${pt + ih + 16}" font-size="11" text-anchor="middle" fill="var(--faint)">${sgn(v * xm)}</text>`;
  }
  g += `<text x="${pl + iw / 2}" y="${H - 6}" font-size="11.5" text-anchor="middle" fill="var(--muted)">← 최근 ${XW[st.xw][0]} 주가 하락 · 상승 →</text>`;
  if (y1 > 0) g += `<text x="${pl + 6}" y="${pt - 10}" font-size="11.5" fill="var(--muted)">↑ ${esc(L.up)}</text>`;
  if (y0 < 0) g += `<text x="${pl + 6}" y="${pt + ih + 30}" font-size="11.5" fill="var(--muted)">↓ ${esc(L.dn)}</text>`;
  // 구역 이름
  const qlab = (q, txt, color) => {
    const [a, b, c, d] = ZOOM[q];
    if (Math.min(b, x1) <= Math.max(a, x0) || Math.min(d, y1) <= Math.max(c, y0)) return '';
    const left = q === 'tl' || q === 'bl', top = q === 'tl' || q === 'tr';
    const x = left ? sx(Math.max(a, x0)) + 12 : sx(Math.min(b, x1)) - 12, y = top ? sy(Math.min(d, y1)) + 22 : sy(Math.max(c, y0)) - 12;
    return `<text x="${x}" y="${y}" font-size="${W < 600 ? 12 : 14}" font-weight="800" text-anchor="${left ? 'start' : 'end'}" fill="${color}">${esc(txt)}</text>`;
  };
  g += qlab('tl', L.tl, up) + qlab('br', L.br, dn) + qlab('tr', '둘 다 좋음', 'var(--faint)') + qlab('bl', '둘 다 나쁨', 'var(--faint)');
  // 점
  const vis = P.filter(p => p.xN >= x0 && p.xN <= x1 && p.yN >= y0 && p.yN <= y1).sort((a, b) => (b.r.mcap || 0) - (a.r.mcap || 0));
  const maxM = Math.max(...vis.map(p => p.r.mcap || 0), 1);
  const k = vis.length > 400 ? 18 : vis.length > 150 ? 24 : 32;
  const hot = new Set([...pick(P, 'tl'), ...pick(P, 'br')].map(p => p.r.t));
  let dots = '', labs = '';
  const zoomK = st.zoom ? 1.25 : 1;
  for (const p of vis) {
    const rad = (2.5 + Math.sqrt((p.r.mcap || 0) / maxM) * k) * zoomK, cx = sx(p.xN), cy = sy(p.yN);
    const col = p.quad === 'tl' ? up : p.quad === 'br' ? dn : 'var(--faint)';
    const fade = trail && p.r.t !== st.sel;   // 경로를 볼 때는 다른 점을 흐리게
    const op = trail && p.r.t === st.sel ? 0.35 : (p.quad === 'tl' || p.quad === 'br' ? 0.72 : 0.32) * (fade ? 0.22 : 1);   // 선택한 점은 비쳐 보이게 (안쪽 경로가 가리지 않도록)
    const ring = p.r.t === st.sel ? `stroke="var(--ink)" stroke-width="2.5"` : p.mine ? `stroke="var(--ink)" stroke-width="1.5"` : `stroke="${col}" stroke-opacity="${fade ? 0.18 : 0.9}" stroke-width="1"`;
    dots += `<circle class="dot" data-t="${esc(p.r.t)}" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad.toFixed(1)}" fill="${col}" fill-opacity="${op}" ${ring}/>`;
    p._cx = cx; p._cy = cy; p._r = rad;
  }
  const labN = trail ? 0 : st.zoom ? 26 : W < 600 ? 10 : 22;
  const lab = vis.filter((p, i) => i < labN || (!trail && (hot.has(p.r.t) || p.mine)) || p.r.t === st.sel);
  const tl = trail ? trailLayer(trail, L, P, sx, sy, [x0, x1, y0, y1]) : '';
  for (const p of lab) {
    const strong = hot.has(p.r.t) || p.r.t === st.sel;
    labs += `<text x="${(p._cx + p._r + 3).toFixed(1)}" y="${(p._cy + 4).toFixed(1)}" font-size="${strong ? 12.5 : 11}" font-weight="${strong ? 800 : 600}" fill="var(--ink)" paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round" pointer-events="none">${esc(p.r.ko && st.zoom && p._r >= 16 && p.r.ko.length <= 6 ? p.r.ko : p.r.t)}</text>`;
  }
  return { svg: g + dots + tl + labs, n: vis.length };
}

// 경로: 지도와 같은 기준(선택한 기간의 주가 × 그 시점의 신호)으로 과거 위치를 계산해 이어 그림. 끝점 = 지금 점
const XI = { r1w: 1, r1m: 2, r3m: 3, r6m: 4 };
function trailCoords(pts, L, P) {
  const xm = XW[st.xw][1], xi = XI[st.xw], cur = P.find(p => p.r.t === st.sel);
  const jit = L.jitter ? hash(st.sel) * 0.14 : 0;
  let C = pts.filter(q => q[xi] != null).map(q => ({
    d: q[0], xN: Math.max(-1, Math.min(1, q[xi] / xm)), yN: Math.max(-1, Math.min(1, (L.raw ? q[5] : q[5] / L.max) + jit)),
  }));
  if (cur) {                                   // 마지막 날짜가 오늘(최근 거래일)이면 지금 점으로 바꾸고, 분기 자료면 지금 점을 덧붙임
    const now = { d: U.asof, xN: cur.xN, yN: cur.yN, now: true };
    if (C.length && C[C.length - 1].d >= U.asof) C[C.length - 1] = now; else C.push(now);
  }
  return C;
}
function trailLayer(pts, L, P, sx, sy, dom) {
  const C = trailCoords(pts, L, P);
  if (C.length < 2) return '';
  const cur = P.find(p => p.r.t === st.sel);
  const [x0, x1, y0, y1] = dom, cl = (v, a, b) => Math.max(a, Math.min(b, v));
  const XY = C.map(c => [sx(cl(c.xN, x0, x1)), sy(cl(c.yN, y0, y1))]);
  const n = XY.length, ink = 'var(--ink)';
  const op = i => 0.16 + 0.84 * (i / (n - 1)) ** 1.2;          // 과거는 연하게, 지금에 가까울수록 진하게
  let g = '<g pointer-events="none">';
  for (let i = 1; i < n; i++) {
    const [ax, ay] = XY[i - 1], [bx, by] = XY[i];
    const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy);
    if (len < 2) continue;
    const r0 = 5, r1 = i === n - 1 ? (cur ? cur._r || 8 : 8) + 5 : 6;     // 점에 붙지 않게 양 끝을 띄움
    if (len <= r0 + r1 + 4) continue;
    const ux = dx / len, uy = dy / len;
    const sxp = ax + ux * r0, syp = ay + uy * r0, ex = bx - ux * r1, ey = by - uy * r1;
    const o = op(i), w = (1.1 + 1.1 * i / (n - 1)).toFixed(2);
    // 화살촉: 얇고 작은 V자 (선과 같은 투명도)
    const ah = 6, aw = 3.2, hx = ex - ux * ah, hy = ey - uy * ah;
    g += `<line x1="${sxp.toFixed(1)}" y1="${syp.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${ink}" stroke-opacity="${o.toFixed(2)}" stroke-width="${w}" stroke-linecap="round"/>`;
    g += `<polyline points="${(hx - uy * aw).toFixed(1)},${(hy + ux * aw).toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)} ${(hx + uy * aw).toFixed(1)},${(hy - ux * aw).toFixed(1)}" fill="none" stroke="${ink}" stroke-opacity="${o.toFixed(2)}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  XY.forEach(([x, y], i) => {
    if (i === n - 1) return;                  // 끝점은 지도 위 실제 점이 그 자리
    const o = op(i);
    g += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.6" fill="${ink}" fill-opacity="${(o * 0.9).toFixed(2)}"/>`;
    g += `<text x="${(x + 7).toFixed(1)}" y="${(y - 6).toFixed(1)}" font-size="10.5" fill="${ink}" fill-opacity="${Math.max(0.45, o).toFixed(2)}" paint-order="stroke" stroke="var(--card)" stroke-width="3">${esc(C[i].d.slice(5).replace('-', '/'))}</text>`;
  });
  return g + '</g>';
}

function pick(P, q, n = 8) {
  // 시가총액 100억 달러 이상을 먼저 (작은 종목은 전망치가 몇 배씩 튀는 경우가 많음), 모자라면 나머지로 채움
  const c = P.filter(p => p.quad === q && Math.abs(p.yC) > 0.06 && Math.abs(p.xN) > 0.06).sort((a, b) => b.score - a.score);
  const big = c.filter(p => (p.r.mcap || 0) >= 1e10);
  return big.length >= n ? big.slice(0, n) : big.concat(c.filter(p => (p.r.mcap || 0) < 1e10)).slice(0, n);
}

function side(P) {
  const L = LENS[st.lens];
  if (st.sel) {
    const r = S.find(x => x.t === st.sel);
    if (r) {
      const tr = st.trail && L.trail ? (st.trail[L.trail] || null) : null;
      return `<div class="card"><div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap"><h3 style="font-size:18px">${esc(r.t)}</h3><span class="mut s13">${esc(r.ko || r.n)}</span><button class="btn" id="unsel" style="margin-left:auto;min-height:30px;padding:2px 10px">닫기</button></div>
        <div class="kv"><div><span>최근 ${XW[st.xw][0]} 주가</span><b>${pctS(r[st.xw])}</b></div><div><span>${esc(L.name)}</span><b>${L.y(r) == null ? '-' : esc(L.v(r))}</b></div>
        <div><span>시가총액</span><b>${fmtUsd(r.mcap)}</b></div><div><span>다음 실적</span><b>${esc(r.c_next || '-')}</b></div></div>
        ${r.s1 ? `<p class="s13" style="margin:0">${esc(r.s1)}</p>` : ''}
        <div class="small mut">${!L.trail ? '내부자 렌즈는 경로 대신 종목 화면의 거래 목록을 보세요.' : tr ? `${esc(tr[0][0])}부터 지금까지 지도 위에서 지나온 길을 그렸어요. 연한 점이 과거, 진한 쪽이 최근이에요.` : st.trail ? '이 종목은 이 렌즈의 경로 자료가 없어요.' : '경로 불러오는 중…'}</div>
        <a class="btn dark" href="${stockUrl(r.t)}" style="text-align:center;text-decoration:none">${esc(r.t)} 종목 화면 →</a> ${starBtn(r.t)}</div>`;
    }
  }
  const row = p => `<a data-pick="${esc(p.r.t)}"><b>${esc(p.r.t)}</b><small>${esc(p.r.ko || p.r.n || '')}</small><span class="v">${sgn(p.x)} · ${esc(L.v(p.r))}</span></a>`;
  const tl = pick(P, 'tl'), br = pick(P, 'br');
  return `<div class="card"><h3>어떻게 읽나요</h3><p class="s13 mut" style="margin:0">${esc(L.desc)}</p><p class="small faint" style="margin:0">구역을 누르면 확대, 점을 누르면 그 종목이 지나온 경로를 그려요.</p></div>
    <div class="card"><h3 style="color:var(--up)">${esc(L.tl)}</h3><div class="mx-list">${tl.map(row).join('') || '<span class="mut s13">해당 종목이 없어요</span>'}</div></div>
    <div class="card"><h3 style="color:var(--dn)">${esc(L.br)}</h3><div class="mx-list">${br.map(row).join('') || '<span class="mut s13">해당 종목이 없어요</span>'}</div></div>`;
}

function render() {
  const L = LENS[st.lens];
  const P = points();
  const box = $('#mx-chart');
  W = Math.max(320, box ? box.clientWidth : Math.min(window.innerWidth - 32, 1160 - 346));
  H = W < 600 ? Math.round(W * 1.05) : Math.min(680, Math.round(W * 0.72));
  const sel = st.sel ? S.find(x => x.t === st.sel) : null;
  const trailPts = sel && L.trail && st.trail ? st.trail[L.trail] : null;
  const showTrail = !!(trailPts && trailPts.length >= 1);
  const d = draw(P, showTrail ? trailPts : null);
  $('#mx-ctl').innerHTML = controls();
  $('#mx-chart').innerHTML = `<div class="mx-bar">${st.zoom ? '<button class="btn" id="unzoom">← 전체 보기</button>' : ''}${showTrail ? `<span class="tag" style="background:var(--card)">${esc(sel.t)} 경로</span><button class="btn" id="untrail">경로 닫기</button>` : ''}</div>
    <svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="어긋남 지도: 가로 최근 ${XW[st.xw][0]} 주가, 세로 ${esc(L.name)}">${d.svg}</svg><div class="mx-tip" id="mx-tip"></div>`;
  $('#mx-side').innerHTML = side(P);
  $('#mx-count').textContent = `${d.n.toLocaleString()}개 종목${st.zoom ? ' (확대)' : ''} · ${U.asof} 기준`;
  bind(P);
  sync();
}

async function select(t) {
  st.sel = t; st.trail = null; render();
  try { const d = await Data.stock(t); if (st.sel === t) { st.trail = d.trail || {}; render(); } } catch (e) { st.trail = {}; render(); }
}

function bind(P) {
  document.querySelectorAll('[data-lens]').forEach(b => b.onclick = () => { st.lens = b.dataset.lens; render(); });
  document.querySelectorAll('[data-xw]').forEach(b => b.onclick = () => { st.xw = b.dataset.xw; render(); });
  document.querySelectorAll('[data-only]').forEach(b => b.onclick = () => { st.only = b.dataset.only; st.zoom = null; render(); });
  $('#f-sec').onchange = e => { st.sec = e.target.value; render(); };
  $('#f-cap').onchange = e => { st.cap = +e.target.value; render(); };
  document.querySelectorAll('.qbg').forEach(r => r.onclick = () => { st.zoom = r.dataset.q; render(); });
  document.querySelectorAll('[data-pick]').forEach(a => a.onclick = e => { e.preventDefault(); select(a.dataset.pick); });
  const uz = $('#unzoom'); if (uz) uz.onclick = () => { st.zoom = null; render(); };
  const ut = $('#untrail'); if (ut) ut.onclick = () => { st.sel = null; st.trail = null; render(); };
  const us = $('#unsel'); if (us) us.onclick = () => { st.sel = null; st.trail = null; render(); };
  const svg = $('#mx-chart svg'), tip = $('#mx-tip'), L = LENS[st.lens];
  const byT = new Map(P.map(p => [p.r.t, p]));
  svg.addEventListener('click', e => { const t = e.target.dataset && e.target.dataset.t; if (t) select(t); });
  svg.addEventListener('mousemove', e => {
    const t = e.target.dataset && e.target.dataset.t, p = t && byT.get(t);
    if (!p) { tip.style.display = 'none'; return; }
    const rc = $('#mx-chart').getBoundingClientRect();
    tip.innerHTML = `<b>${esc(p.r.t)}</b> ${esc(p.r.ko || p.r.n || '')}<br>주가 ${XW[st.xw][0]} ${sgn(p.x, 1)} · ${esc(L.v(p.r))}<br>시가총액 ${fmtUsd(p.r.mcap)}`;
    tip.style.display = 'block';
    const x = e.clientX - rc.left + 14, y = e.clientY - rc.top + 14;
    tip.style.left = Math.min(x, rc.width - tip.offsetWidth - 8) + 'px'; tip.style.top = Math.min(y, rc.height - tip.offsetHeight - 8) + 'px';
  });
  svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
}

(async () => {
  try { U = await Data.universe(); }
  catch (e) { $('#app').innerHTML = `<div class="loading">불러오지 못했습니다 (${esc(e.message)})</div>`; return; }
  S = U.rows.filter(r => r.k === 'stock');
  $('#app').innerHTML = `<div class="hero"><h1>어긋남 지도</h1><p>주가와 신호가 반대로 간 종목을 찾는 지도 · 가로 = 주가, 세로 = 고른 신호, 점 크기 = 시가총액 · <span id="mx-count"></span></p></div>
    <div class="card" id="mx-ctl" style="gap:10px"></div>
    <div class="mx-wrap"><div class="mx-chart" id="mx-chart"></div><div class="mx-side" id="mx-side"></div></div>
    <div class="small faint">정보 제공용이며 투자 권유가 아닙니다 · 가로축 범위 밖의 종목은 가장자리에 붙여 그립니다 · 출처: SEC EDGAR(재무·내부자·13F), FINRA(공매도), yfinance(가격·컨센서스)</div>`;
  if (st.sel) select(st.sel); else render();
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 150); });
  document.addEventListener('watch-change', render);
  footer();
})();
