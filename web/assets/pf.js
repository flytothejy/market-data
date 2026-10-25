// 관심 포트폴리오 계산 — 종목별 주간 수정종가(배당·분할 반영, build.py detail.wk)로
// 과거 시뮬레이션 · 만든 뒤 성과 · 지표 · 기여도 · 선 그래프
const PFX = {
  BENCH: [['SPY', 'S&P 500'], ['QQQ', '나스닥 100']],
  COLORS: ['var(--accent)', '#0d9488', '#7c3aed'],
  BCOL: { SPY: '#8a8984', QQQ: '#c4c3bd' },
  PER: [['1y', '1년', 1], ['3y', '3년', 3], ['5y', '5년', 5], ['10y', '10년', 10]],

  // ---- 진단: ETF 안까지 펼친 실제 노출 (ETF 구성은 공개된 상위 종목만 있는 경우가 많아 나머지는 따로 셈)
  SEC_KEY: { technology: 'Technology', healthcare: 'Healthcare', financial_services: 'Financial Services', consumer_cyclical: 'Consumer Cyclical', consumer_defensive: 'Consumer Defensive', industrials: 'Industrials', energy: 'Energy', utilities: 'Utilities', realestate: 'Real Estate', basic_materials: 'Basic Materials', communication_services: 'Communication Services' },
  CAPS: ['초대형 (2,000억 달러 이상)', '대형 (100억~2,000억)', '중형 (20억~100억)', '소형 (20억 미만)', '분류 안 됨'],
  async etfs(items, byT) {
    const out = {};
    await Promise.all(items.filter(x => byT[x.t] && byT[x.t].k === 'etf').map(async x => { try { out[x.t] = await Data.etf(x.t); } catch (e) { } }));
    return out;
  },
  look(items, byT, E) {
    const W = items.reduce((a, x) => a + (x.w > 0 ? x.w : 0), 0) || 1;
    const exp = {}, sec = {}, cls = {}, cap = {}, add = (m, k, v) => { if (v > 0) m[k] = (m[k] || 0) + v; };
    let rest = 0, etfW = 0;
    const capB = mc => mc == null ? this.CAPS[4] : mc >= 2e11 ? this.CAPS[0] : mc >= 1e10 ? this.CAPS[1] : mc >= 2e9 ? this.CAPS[2] : this.CAPS[3];
    const stock = (t, w, via) => {
      const r = byT[t], e = exp[t] = exp[t] || { t, w: 0, direct: 0, via: {} };
      e.w += w; if (via) e.via[via] = (e.via[via] || 0) + w; else e.direct += w;
      add(cap, r && r.k !== 'etf' ? capB(r.mcap) : this.CAPS[4], w);
    };
    for (const x of items) {
      if (!(x.w > 0)) continue;
      const w = x.w / W, r = byT[x.t];
      if (!r) { add(cls, '분류 안 됨', w); add(sec, '분류 안 됨', w); continue; }
      if (r.k !== 'etf') { stock(x.t, w); add(cls, '주식', w); add(sec, secKo(r.sec), w); continue; }
      etfW += w;
      const d = E[x.t], a = d && d.assets, hs = (d && d.holdings) || [];
      if (!d || (!a && !hs.length && !d.sectors)) { add(cls, '분류 안 됨', w); add(sec, '분류 안 됨', w); add(cap, this.CAPS[4], w); continue; }
      const S = a ? (a.stockPosition || 0) + (a.preferredPosition || 0) : 1, B = a ? a.bondPosition || 0 : 0, C = a ? a.cashPosition || 0 : 0, O = a ? (a.otherPosition || 0) + (a.convertiblePosition || 0) : 0;
      add(cls, '주식', w * S); add(cls, '채권', w * B); add(cls, '현금', w * C); add(cls, '기타 자산 (금 등)', w * O);
      if (d.sectors) { const tot = Object.values(d.sectors).reduce((p, q) => p + q, 0) || 1; for (const [k, v] of Object.entries(d.sectors)) add(sec, secKo(this.SEC_KEY[k] || k), w * S * v / tot); }
      else add(sec, '분류 안 됨', w * S);
      add(sec, '채권', w * B); add(sec, '현금', w * C); add(sec, '기타 자산 (금 등)', w * O);
      let cov = 0;
      for (const [h, , pct] of hs) { const hw = w * S * Math.min(1, (+pct || 0) / 100 / Math.max(S, 1e-9)); if (!(hw > 0)) continue; cov += hw; stock(String(h).replace('.', '-'), hw, x.t); }
      const rem = Math.max(0, w * S - cov); rest += rem; add(cap, this.CAPS[4], rem);
    }
    return { exp: Object.values(exp).sort((a, b) => b.w - a.w), sec, cls, cap, rest, etfW };
  },
  // 가중 특징: 펼친 종목 기준(선행 PER은 이익수익률로 평균), 배당·1년 수익률은 담은 종목(ETF 그대로) 기준
  chars(L, items, byT) {
    const W = items.reduce((a, x) => a + (x.w > 0 ? x.w : 0), 0) || 1;
    const avg = (f, pos) => { let s = 0, n = 0; for (const e of L.exp) { const r = byT[e.t]; if (!r || r.k === 'etf') continue; const v = f(r); if (v == null || !isFinite(v) || (pos && v <= 0)) continue; s += e.w * v; n += e.w; } return n ? s / n : null; };
    const ey = avg(r => { const pe = r.c_fpe ?? r.pe; return pe > 0 ? 1 / pe : null; });
    const item = f => { let s = 0, n = 0; for (const x of items) { const r = byT[x.t]; if (!r || !(x.w > 0)) continue; const v = f(r); if (v == null) continue; s += x.w / W * v; n += x.w / W; } return n ? s / n : null; };
    const known = L.exp.filter(e => byT[e.t] && byT[e.t].k !== 'etf').reduce((a, e) => a + e.w, 0);
    const stockW = Object.entries(L.cls).filter(([k]) => k === '주식').reduce((a, [, v]) => a + v, 0) || (1 - L.etfW);
    return { fpe: ey ? 1 / ey : null, rev_g: avg(r => r.rev_g), om: avg(r => r.om), dy: item(r => r.dy), r1y: item(r => r.r1y), cov: stockW ? Math.min(1, known / stockW) : 0 };
  },
  conc(L) {
    const top5 = L.exp.slice(0, 5).reduce((a, e) => a + e.w, 0), hh = L.exp.reduce((a, e) => a + e.w * e.w, 0);
    return { top5, effN: hh ? 1 / hh : null };
  },
  // 두 분포를 나란히 막대로 (mine vs ref)
  bars2(mine, ref, keys, refName) {
    const mx = Math.max(...keys.map(k => Math.max(mine[k] || 0, ref ? ref[k] || 0 : 0)), 0.01);
    return `<div class="pf-b2">${keys.map(k => { const a = mine[k] || 0, b = ref ? ref[k] || 0 : null; return `<div class="r"><span class="k">${esc(k)}</span><div class="bb"><i class="me" style="width:${a / mx * 100}%"></i>${b != null ? `<i class="rf" style="width:${b / mx * 100}%"></i>` : ''}</div><span class="v num">${(a * 100).toFixed(1)}%${b != null ? `<small>${(b * 100).toFixed(1)}%</small>` : ''}</span></div>`; }).join('')}</div>`;
  },

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
  // opt: { dca: 매달 넣는 금액(표시 통화), fx: 원/달러 배열(있으면 원화로 표시), end: 끝 위치(포함) }
  // rb: 'none' | 'q'(분기) | 'y'(연 1회) | 'band'(목표 비중에서 5%p 넘게 벗어나면)
  run(items, A, dates, i0, cap = 10000, rb = 'none', opt = {}) {
    const its = items.filter(x => x.w > 0 && A[x.t]);
    const missing = items.filter(x => x.w > 0 && !A[x.t]).map(x => x.t);
    if (!its.length) return null;
    const fx = opt.fx || null, end = Math.min(dates.length - 1, opt.end ?? dates.length - 1);
    // 모든 종목 값(원화면 환율도)이 있는 첫 주부터 (늦게 상장한 종목이 있으면 시작이 늦어짐)
    let s = i0; const late = [];
    for (const x of its) { let k = s; while (k <= end && A[x.t][k] == null) k++; if (k > s) late.push(x.t); s = Math.max(s, k); }
    if (fx) while (s <= end && fx[s] == null) s++;
    if (s >= end) return { missing, late, empty: true };
    const W = its.reduce((a, x) => a + x.w, 0), wt = its.map(x => x.w / W), F = i => fx ? fx[i] : 1;
    const P = (k, i) => A[its[k].t][i];
    const first = opt.dca ? opt.dca : cap;                       // 표시 통화 기준 첫 투입
    let units = its.map((x, k) => first / F(s) * wt[k] / P(k, s)), inv = first, nrb = 0;
    const v = [], d = [], iv = [], flows = [[dates[s], -first]], contrib = its.map(() => 0);
    const q = day => day.slice(0, 4) + Math.floor((+day.slice(5, 7) - 1) / 3);
    for (let i = s; i <= end; i++) {
      if (i > s) {
        if (!opt.dca) its.forEach((x, k) => { contrib[k] += units[k] * (P(k, i) - P(k, i - 1)) / (cap / F(s)); });
        if (opt.dca && dates[i].slice(0, 7) !== dates[i - 1].slice(0, 7)) {     // 매달 첫 주에 목표 비중대로 삼
          const usd = opt.dca / F(i); units = units.map((u, k) => u + usd * wt[k] / P(k, i)); inv += opt.dca; flows.push([dates[i], -opt.dca]);
        }
      }
      const usdV = its.reduce((a, x, k) => a + units[k] * P(k, i), 0);
      v.push(usdV * F(i)); d.push(dates[i]); iv.push(inv);
      if (i < end && rb !== 'none') {
        let go = false;
        if (rb === 'q') go = q(dates[i + 1]) !== q(dates[i]);
        else if (rb === 'y') go = dates[i + 1].slice(0, 4) !== dates[i].slice(0, 4);
        else if (rb === 'band') go = its.some((x, k) => Math.abs(units[k] * P(k, i) / usdV - wt[k]) > 0.05);
        if (go) { units = its.map((x, k) => usdV * wt[k] / P(k, i)); nrb++; }
      }
    }
    flows.push([dates[end], v[v.length - 1]]);
    return { d, v, iv, inv, flows, nrb, missing, late, start: dates[s], contrib: its.map((x, k) => ({ t: x.t, w: wt[k], c: opt.dca ? null : contrib[k] })) };
  },
  bench(A, dates, i0, t, opt = {}) { return A[t] ? this.run([{ t, w: 1 }], A, dates, i0, 10000, 'none', opt) : null; },
  // 돈을 나눠 넣은 경우의 연 환산 수익률 (내부수익률)
  xirr(flows) {
    const t0 = Date.parse(flows[0][0]), f = r => flows.reduce((a, [d, c]) => a + c / Math.pow(1 + r, (Date.parse(d) - t0) / 31557600000), 0);
    let lo = -0.99, hi = 10; if (f(lo) * f(hi) > 0) return null;
    for (let k = 0; k < 80; k++) { const m = (lo + hi) / 2; if (f(lo) * f(m) <= 0) hi = m; else lo = m; }
    return (lo + hi) / 2;
  },
  // 위기 구간: [이름, 시작(S&P 고점 무렵), 바닥 무렵]
  CRISES: [['2008 금융위기', '2007-10-09', '2009-03-09'], ['2020 코로나 폭락', '2020-02-19', '2020-03-23'], ['2022 금리 인상기', '2022-01-03', '2022-10-12']],
  // 구간 시작 가치 대비 바닥까지 최대 하락, 시작 가치를 되찾은 날
  crisis(x, from, to) {
    if (!x || x.empty || !x.v || x.start > from) return null;
    const a = x.d.findIndex(d => d >= from); if (a < 0) return null;
    let b = x.d.findIndex(d => d > to); if (b < 0) b = x.d.length;
    let mn = 0; for (let i = a; i < b; i++) mn = Math.min(mn, x.v[i] / x.v[a] - 1);
    let rec = null; for (let i = a + 1; i < x.d.length; i++) if (i >= b && x.v[i] >= x.v[a]) { rec = x.d[i]; break; }
    return { dd: mn, rec, months: rec ? Math.round((Date.parse(rec) - Date.parse(x.d[a])) / (30.44 * 864e5)) : null };
  },
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
    const ab = !!opt.abs, P = lines.map(l => { const m = {}; l.d.forEach((d, i) => m[d] = ab ? l.v[i] : l.v[i] / l.v[0] - 1); return dates.map(d => m[d] ?? null); });
    const yl = v => ab ? opt.fmt(v) : (v * 100).toFixed(Math.abs(v) < 0.1 && v ? 1 : 0) + '%', tl = v => ab ? opt.fmt(v) : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
    const draw = () => {
      const W = Math.max(280, el.clientWidth || 600), H = opt.h || 240, L = 6, R = 58, T = 12, B = 24;
      const all = P.flat().filter(v => v != null); let lo = Math.min(0, ...all), hi = Math.max(0, ...all); if (!ab && hi - lo < 0.02) { hi += 0.01; lo -= 0.01; } if (ab && hi === lo) hi = lo + 1;
      const X = i => L + (dates.length < 2 ? 0 : i / (dates.length - 1)) * (W - L - R), Y = v => T + (hi - v) / (hi - lo) * (H - T - B);
      const step = (hi - lo) / 4, mag = Math.pow(10, Math.floor(Math.log10(step))), nice = [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= step) || step;
      let g = '';
      for (let v = Math.ceil(lo / nice) * nice; v <= hi + 1e-9; v += nice) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line2)"/><text x="${W - R + 6}" y="${(Y(v) + 4).toFixed(1)}" font-size="10.5" fill="var(--faint)">${yl(v)}</text>`;
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
        tip.innerHTML = `<b>${dates[i]}</b>` + lines.map((l, k) => P[k][i] == null ? '' : `<div><i style="background:${l.color}"></i>${esc(l.name)} <b class="${ab ? '' : cls(P[k][i])}">${tl(P[k][i])}</b></div>`).join('');
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
