// 관심 포트폴리오 계산 — 종목별 주간 수정종가(배당·분할 반영, build.py detail.wk)로
// 과거 시뮬레이션 · 만든 뒤 성과 · 지표 · 기여도 · 선 그래프
const PFX = {
  BENCH: [['SPY', 'S&P 500'], ['QQQ', '나스닥 100']],
  COLORS: ['var(--accent)', '#0d9488', '#7c3aed'],
  BCOL: { SPY: '#8a8984', QQQ: '#c4c3bd' },
  PER: [['1y', '1년', 1], ['3y', '3년', 3], ['5y', '5년', 5], ['10y', '10년', 10]],

  // 종목별 주간 시계열 { t: {d:[], c:[]} } — 없는 종목은 빠짐
  async series(tickers, byT) {
    const out = {};
    await Promise.all([...new Set(tickers)].map(async t => {
      try {
        const k = byT[t] ? byT[t].k : (['SPY', 'QQQ'].includes(t) ? 'etf' : 'stock');
        const j = await (k === 'etf' ? Data.etf(t) : Data.stock(t));
        if (j && j.wk && j.wk.d && j.wk.d.length) out[t] = j.wk;
      } catch (e) { }
    }));
    return out;
  },
  // 기준 날짜(dates)에 맞춰 각 종목 값을 펼침 (그 날 이전 마지막 값, 상장 전은 null)
  align(w, dates) {
    const out = new Array(dates.length).fill(null);
    let j = 0, last = null;
    for (let i = 0; i < dates.length; i++) {
      while (j < w.d.length && w.d[j] <= dates[i]) { last = w.c[j]; j++; }
      out[i] = last;
    }
    return out;
  },
  idxOn(dates, day) { let i = 0; while (i + 1 < dates.length && dates[i + 1] <= day) i++; return i; },   // day 이전(같은 날 포함) 마지막 주
  // 포트폴리오 가치 흐름. items [{t, w}], A = {t: aligned[]}, i0 = 시작 위치, rb = 'none' | 'q'
  run(items, A, dates, i0, cap = 10000, rb = 'none') {
    const its = items.filter(x => x.w > 0 && A[x.t]);
    const missing = items.filter(x => x.w > 0 && !A[x.t]).map(x => x.t);
    if (!its.length) return null;
    // 모든 종목 값이 있는 첫 주부터 (늦게 상장한 종목이 있으면 시작이 늦어짐)
    let s = i0; const late = [];
    for (const x of its) { let k = s; while (k < dates.length && A[x.t][k] == null) k++; if (k > s) { late.push(x.t); } s = Math.max(s, k); }
    if (s >= dates.length - 1) return { missing, late, empty: true };
    const W = its.reduce((a, x) => a + x.w, 0), wt = its.map(x => x.w / W);
    let units = its.map((x, k) => cap * wt[k] / A[x.t][s]);
    const v = [], d = [], contrib = its.map(() => 0);
    const q = day => day.slice(0, 4) + Math.floor((+day.slice(5, 7) - 1) / 3);
    for (let i = s; i < dates.length; i++) {
      if (i > s) its.forEach((x, k) => { contrib[k] += units[k] * (A[x.t][i] - A[x.t][i - 1]) / cap; });
      const val = its.reduce((a, x, k) => a + units[k] * A[x.t][i], 0);
      v.push(val); d.push(dates[i]);
      if (rb === 'q' && i + 1 < dates.length && q(dates[i + 1]) !== q(dates[i])) units = its.map((x, k) => val * wt[k] / A[x.t][i]);
    }
    return { d, v, missing, late, start: dates[s], contrib: its.map((x, k) => ({ t: x.t, w: wt[k], c: contrib[k] })) };
  },
  bench(A, dates, i0, t) { return A[t] ? this.run([{ t, w: 1 }], A, dates, i0) : null; },
  rets(v) { const r = []; for (let i = 1; i < v.length; i++) r.push(v[i] / v[i - 1] - 1); return r; },
  // 지표: 수익률·연평균·변동성(주간×√52)·최대 낙폭·샤프(무위험 0)·베타(대비 b)
  metrics(x, b) {
    if (!x || !x.v || x.v.length < 2) return null;
    const v = x.v, r = this.rets(v), n = r.length;
    const tot = v[n] / v[0] - 1, yrs = (Date.parse(x.d[n]) - Date.parse(x.d[0])) / 31557600000;
    const mean = r.reduce((a, y) => a + y, 0) / n, sd = Math.sqrt(r.reduce((a, y) => a + (y - mean) ** 2, 0) / Math.max(1, n - 1));
    let pk = v[0], mdd = 0; for (const y of v) { pk = Math.max(pk, y); mdd = Math.min(mdd, y / pk - 1); }
    const out = { tot, cagr: yrs >= 0.95 ? Math.pow(1 + tot, 1 / yrs) - 1 : null, vol: n >= 8 ? sd * Math.sqrt(52) : null, mdd, sharpe: n >= 8 && sd ? mean * 52 / (sd * Math.sqrt(52)) : null, beta: null };
    if (b && b.v && n >= 8) {
      const bm = {}; b.d.forEach((d, i) => bm[d] = b.v[i]);
      const pr = []; for (let i = 1; i <= n; i++) { const a = bm[x.d[i - 1]], c = bm[x.d[i]]; if (a && c) pr.push([r[i - 1], c / a - 1]); }
      if (pr.length >= 8) {
        const mx = pr.reduce((a, p) => a + p[0], 0) / pr.length, my = pr.reduce((a, p) => a + p[1], 0) / pr.length;
        const cov = pr.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0), vy = pr.reduce((a, p) => a + (p[1] - my) ** 2, 0);
        out.beta = vy ? cov / vy : null;
      }
    }
    return out;
  },
  // 선 그래프 (시작 = 0%, 수익률 축). lines [{name, color, d, v, bold}]
  chart(el, lines, opt = {}) {
    lines = lines.filter(l => l && l.v && l.v.length >= 2);
    if (!lines.length) { el.innerHTML = `<div class="mut s13" style="padding:20px 0">${opt.empty || '그릴 자료가 없어요'}</div>`; return; }
    const dates = [...new Set(lines.flatMap(l => l.d))].sort();
    const P = lines.map(l => { const m = {}; l.d.forEach((d, i) => m[d] = l.v[i] / l.v[0] - 1); return dates.map(d => m[d] ?? null); });
    const draw = () => {
      const W = Math.max(280, el.clientWidth || 600), H = opt.h || 240, L = 6, R = 58, T = 12, B = 24;
      const all = P.flat().filter(v => v != null); let lo = Math.min(0, ...all), hi = Math.max(0, ...all); if (hi - lo < 0.02) { hi += 0.01; lo -= 0.01; }
      const X = i => L + (dates.length < 2 ? 0 : i / (dates.length - 1)) * (W - L - R), Y = v => T + (hi - v) / (hi - lo) * (H - T - B);
      const step = (hi - lo) / 4, mag = Math.pow(10, Math.floor(Math.log10(step))), nice = [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= step) || step;
      let g = '';
      for (let v = Math.ceil(lo / nice) * nice; v <= hi + 1e-9; v += nice) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line2)"/><text x="${W - R + 6}" y="${(Y(v) + 4).toFixed(1)}" font-size="10.5" fill="var(--faint)">${(v * 100).toFixed(Math.abs(nice) < 0.01 ? 1 : 0)}%</text>`;
      g += `<line x1="${L}" x2="${W - R}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--line)"/>`;
      const span = (Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / 864e5, ylab = span > 900;
      let prev = '', px = -99;
      dates.forEach((d, i) => { const key = ylab ? d.slice(0, 4) : d.slice(0, 7); if (key === prev) return; prev = key; const x = X(i); if (i === 0 || x - px < 44 || x > W - R - 24) return; px = x; g += `<text x="${x.toFixed(1)}" y="${H - 6}" font-size="10.5" fill="var(--faint)" text-anchor="middle">${ylab ? key : d.slice(2, 7).replace('-', '.')}</text>`; });
      const path = p => { let s = '', on = false; p.forEach((v, i) => { if (v == null) { on = false; return; } s += (on ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); on = true; }); return s; };
      lines.slice().reverse().forEach((l, ri) => { const k = lines.length - 1 - ri; g += `<path d="${path(P[k])}" fill="none" stroke="${l.color}" stroke-width="${l.bold ? 2.4 : 1.5}" stroke-linejoin="round"/>`; });
      const ends = lines.map((l, k) => { let i = P[k].length - 1; while (i > 0 && P[k][i] == null) i--; return { k, i, y: Y(P[k][i]) }; }).sort((a, b) => a.y - b.y);
      for (let j = 1; j < ends.length; j++) if (ends[j].y - ends[j - 1].y < 13) ends[j].y = ends[j - 1].y + 13;
      ends.forEach(e => { g += `<circle cx="${X(e.i).toFixed(1)}" cy="${Y(P[e.k][e.i]).toFixed(1)}" r="3" fill="${lines[e.k].color}"/>`; });
      el.innerHTML = `<div style="position:relative"><svg width="${W}" height="${H}" style="display:block;overflow:visible">${g}<line class="pfx-h" y1="${T}" y2="${H - B}" stroke="var(--muted)" stroke-width="1" style="display:none"/></svg><div class="pfx-tip"></div></div>`;
      const svg = el.querySelector('svg'), hl = el.querySelector('.pfx-h'), tip = el.querySelector('.pfx-tip');
      const move = e => {
        const rc = svg.getBoundingClientRect(), x = (e.touches ? e.touches[0].clientX : e.clientX) - rc.left;
        const i = Math.max(0, Math.min(dates.length - 1, Math.round((x - L) / (W - L - R) * (dates.length - 1))));
        hl.setAttribute('x1', X(i)); hl.setAttribute('x2', X(i)); hl.style.display = '';
        tip.innerHTML = `<b>${dates[i]}</b>` + lines.map((l, k) => P[k][i] == null ? '' : `<div><i style="background:${l.color}"></i>${esc(l.name)} <b class="${cls(P[k][i])}">${(P[k][i] >= 0 ? '+' : '') + (P[k][i] * 100).toFixed(1)}%</b></div>`).join('');
        tip.style.display = 'block'; const tw = tip.offsetWidth; tip.style.left = Math.min(Math.max(0, X(i) + 10), W - tw) + 'px'; tip.style.top = '4px';
      };
      svg.onmousemove = move; svg.ontouchmove = move; svg.onmouseleave = () => { hl.style.display = 'none'; tip.style.display = 'none'; };
    };
    draw();
    if (!el._ro && window.ResizeObserver) { let w0 = el.clientWidth; el._ro = new ResizeObserver(() => { if (Math.abs(el.clientWidth - w0) > 4) { w0 = el.clientWidth; el._draw && el._draw(); } }); el._ro.observe(el); }
    el._draw = draw;
  },
  legend(lines) { return `<div class="leg-row">${lines.filter(Boolean).map(l => `<span><i style="background:${l.color};width:14px;height:3px;border-radius:2px;display:inline-block;vertical-align:middle;margin-right:5px"></i>${esc(l.name)}</span>`).join('')}</div>`; },
  // 지표 표
  table(rows) {
    const f = (v, k) => v == null ? '<span class="faint">-</span>' : k === 'pct' ? pctS(v) : k === 'pctu' ? `<span class="num">${(v * 100).toFixed(1)}%</span>` : `<span class="num">${v.toFixed(2)}</span>`;
    const H = [['tot', '총 수익률', 'pct'], ['cagr', '연평균', 'pct'], ['vol', '변동성(연)', 'pctu'], ['mdd', '최대 낙폭', 'pct'], ['sharpe', '샤프 지수', 'x'], ['beta', '베타(S&P 500 대비)', 'x']];
    return `<div class="tbl-wrap"><table class="t pfx-t"><thead><tr><th class="l"></th>${H.map(h => `<th>${h[1]}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr><td class="l"><i class="pfx-dot" style="background:${r.color}"></i>${esc(r.name)}</td>${H.map(h => `<td>${r.m ? f(r.m[h[0]], h[2]) : '-'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  },
};
