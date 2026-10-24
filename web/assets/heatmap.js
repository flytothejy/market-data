// 티커맵 — 히트맵 보기 (핀비즈형): 업종 → 세부 업종 → 종목 사각형, 크기 = 시가총액, 색 = 주가 변화 또는 신호
// 시간 재생: 최근 약 3개월 일별 가격(px3m.json)으로 그날까지의 변화를 다시 칠함 (사각형 크기는 지금 시가총액 그대로)
const Heat = (() => {
  const COLOR = {
    r1d: { name: '1일', max: 0.03, n: 1 }, r1w: { name: '1주', max: 0.06, n: 5 }, r1m: { name: '1개월', max: 0.12, n: 21 },
    r3m: { name: '3개월', max: 0.25, n: 63, cum: true }, rytd: { name: '올해', max: 0.35 },
  };
  const SIG = { eps: 'EPS 전망', rev: '매출 가속', guru: '유명 투자자', insider: '내부자', short: '공매도' };   // ui.js LENS_SNAP
  const CAPS = [[0, '전체'], [1e10, '100억 달러 이상'], [1e11, '1,000억 달러 이상']];
  let U, S, box, st, PX = null, LAY = [], frame = null, playing = false, raf = 0, ro = null;

  const qs = new URLSearchParams(location.search);
  const defC = () => (typeof Prefs !== 'undefined' && Prefs.get('heat.color')) || 'r1d';   // 설정의 '히트맵 기본 색'
  st = { c: qs.get('hc') || defC(), cap: qs.has('hcap') ? +qs.get('hcap') : (innerWidth < 700 ? 1e10 : 0), sec: qs.get('hsec') || '' };   // 휴대폰은 처음에 100억 달러 이상만 (칸이 너무 작아짐)
  const sync = () => {
    const u = new URL(location.href), set = (k, v, d) => v && v !== d ? u.searchParams.set(k, v) : u.searchParams.delete(k);
    set('hc', st.c, defC()); set('hcap', String(st.cap), String(innerWidth < 700 ? 1e10 : 0)); set('hsec', st.sec);
    history.replaceState(null, '', u);
  };
  const isSig = () => !!SIG[st.c];

  // ---- 값: 지금 / 재생 중이면 그날
  function valNow(r) {
    if (isSig()) { const L = LENS_SNAP[st.c], y = L.y(r); return y == null ? null : L.raw ? y : Math.max(-1, Math.min(1, y / L.max)); }
    return r[st.c] ?? null;
  }
  function valAt(r, i) {
    const C = PX && PX.t[r.t]; if (!C) return null;
    const c = COLOR[st.c], j = c.cum ? 0 : i - c.n;
    if (j < 0 || C[i] == null || C[j] == null) return null;
    return C[i] / C[j] - 1;
  }
  const val = r => frame != null && !isSig() && COLOR[st.c].n ? valAt(r, Math.round(frame)) : valNow(r);
  const scale = () => isSig() ? 1 : COLOR[st.c].max;

  function fill(v) {
    if (v == null) return 'var(--hm-na)';
    const k = Math.min(1, Math.abs(v) / scale()), p = Math.round(12 + 88 * Math.pow(k, 0.8));
    return `color-mix(in srgb, ${v >= 0 ? 'var(--hm-up)' : 'var(--hm-dn)'} ${p}%, var(--hm-mid))`;
  }
  const label = v => v == null ? '' : isSig() ? (v > 0 ? '+' : '') + (v * 100).toFixed(0) : (v > 0 ? '+' : '') + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + '%';

  // ---- 사각형 나누기 (squarified)
  function squarify(items, x, y, w, h) {
    const out = [], tot = items.reduce((a, b) => a + b.v, 0);
    if (!tot || w <= 0 || h <= 0) return out;
    const sc = w * h / tot, xs = items.map(it => ({ ...it, a: it.v * sc })).filter(it => it.a > 0);
    let row = [], i = 0;
    const worst = (r, side) => { const s = r.reduce((a, b) => a + b.a, 0), mx = Math.max(...r.map(z => z.a)), mn = Math.min(...r.map(z => z.a)); return Math.max(side * side * mx / (s * s), s * s / (side * side * mn)); };
    const lay = r => {
      const s = r.reduce((a, b) => a + b.a, 0);
      if (w >= h) { const cw = s / h; let yy = y; for (const z of r) { const ch = z.a / cw; out.push({ ...z, x, y: yy, w: cw, h: ch }); yy += ch; } x += cw; w -= cw; }
      else { const ch = s / w; let xx = x; for (const z of r) { const cw = z.a / ch; out.push({ ...z, x: xx, y, w: cw, h: ch }); xx += cw; } y += ch; h -= ch; }
    };
    while (i < xs.length) {
      const side = Math.min(w, h), it = xs[i];
      if (!row.length || worst([...row, it], side) <= worst(row, side)) { row.push(it); i++; }
      else { lay(row); row = []; }
    }
    if (row.length) lay(row);
    return out;
  }

  function layout(W, H) {
    const rows = S.filter(r => (r.mcap || 0) >= Math.max(st.cap, 1) && (!st.sec || r.sec === st.sec));
    const bySec = new Map();
    for (const r of rows) { const s = r.sec || '기타', i = r.ind || '기타'; if (!bySec.has(s)) bySec.set(s, new Map()); const m = bySec.get(s); if (!m.has(i)) m.set(i, []); m.get(i).push(r); }
    const secs = [...bySec].map(([s, m]) => ({ id: s, m, v: [...m.values()].flat().reduce((a, r) => a + r.mcap, 0) })).sort((a, b) => b.v - a.v);
    const out = { secs: [], cells: [] };
    for (const sb of squarify(secs, 0, 0, W, H)) {
      const hd = sb.h > 46 && sb.w > 60 ? 17 : 0, G = 1.5;
      out.secs.push({ id: sb.id, x: sb.x, y: sb.y, w: sb.w, h: sb.h, hd });
      const inds = [...sb.m].map(([i, rs]) => ({ id: i, rs, v: rs.reduce((a, r) => a + r.mcap, 0) })).sort((a, b) => b.v - a.v);
      for (const ib of squarify(inds, sb.x + G, sb.y + hd + G, sb.w - 2 * G, sb.h - hd - 2 * G)) {
        const cs = squarify(ib.rs.map(r => ({ id: r.t, r, v: r.mcap })).sort((a, b) => b.v - a.v), ib.x + 1, ib.y + 1, ib.w - 2, ib.h - 2);
        for (const c of cs) out.cells.push({ r: c.r, ind: ib.id, x: c.x, y: c.y, w: c.w, h: c.h });
      }
    }
    return out;
  }

  // ---- 그리기
  function svgOf(W, H, label_sec = true) {
    const cells = LAY.cells.map((c, i) => {
      const v = val(c.r), big = c.w > 30 && c.h > 20, fs = Math.max(9, Math.min(22, Math.sqrt(c.w * c.h) / 4.2));
      return `<g data-i="${i}" class="hm-c"><rect x="${(c.x + .5).toFixed(1)}" y="${(c.y + .5).toFixed(1)}" width="${Math.max(0, c.w - 1).toFixed(1)}" height="${Math.max(0, c.h - 1).toFixed(1)}" fill="${fill(v)}"/>`
        + (big ? `<text x="${(c.x + c.w / 2).toFixed(1)}" y="${(c.y + c.h / 2 - (c.h > fs * 2.6 ? fs * 0.25 : -fs * 0.35)).toFixed(1)}" font-size="${fs.toFixed(1)}" text-anchor="middle" class="hm-t">${esc(c.r.t)}</text>`
          + (c.h > fs * 2.6 ? `<text x="${(c.x + c.w / 2).toFixed(1)}" y="${(c.y + c.h / 2 + fs * 0.85).toFixed(1)}" font-size="${(fs * 0.62).toFixed(1)}" text-anchor="middle" class="hm-v">${label(v)}</text>` : '') : '') + '</g>';
    }).join('');
    const secs = LAY.secs.map(s => `<g class="hm-s" data-sec="${esc(s.id)}"><rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" fill="none" stroke="var(--bg)" stroke-width="3"/>`
      + (s.hd ? `<text x="${s.x + 6}" y="${s.y + 12.5}" class="hm-h">${esc(secKo(s.id))}${st.sec || !label_sec ? '' : ' ›'}</text>` : '') + '</g>').join('');
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="히트맵: 크기 시가총액, 색 ${esc(COLOR[st.c] ? COLOR[st.c].name + ' 주가 변화' : SIG[st.c])}"><rect width="${W}" height="${H}" fill="var(--bg)"/>${cells}${secs}</svg>`;
  }
  function draw() {
    const el = box.querySelector('#hm'); if (!el) return;
    const W = Math.max(320, el.clientWidth), H = Math.round(W < 700 ? W * 1.7 : Math.min(760, Math.max(540, W * 0.6)));
    LAY = layout(W, H);
    el.innerHTML = svgOf(W, H);
    box.querySelector('#hm-n').textContent = `${LAY.cells.length}종목`;
  }
  // 홈용 작은 히트맵: 시가총액 100억 달러 이상, 설정의 기본 색, 조작 없음 (종목을 누르면 종목 화면)
  function mini(el, u, H) {
    U = u; S = U.rows.filter(r => r.k === 'stock' && r.mcap);
    st = { c: defC(), cap: 1e10, sec: '' }; frame = null;
    const W = Math.max(300, el.clientWidth);
    LAY = layout(W, H);
    const c = COLOR[st.c];
    el.innerHTML = `<div class="hm-mini-h"><b>히트맵</b><span class="mut s13">시가총액 100억 달러 이상 · 색 = ${esc(c ? c.name + ' 주가' : '')}</span><span class="hm-sw">${[-1, -0.5, -0.2, 0, 0.2, 0.5, 1].map(k => `<i style="background:${fill(k * scale())}"></i>`).join('')}</span></div>${svgOf(W, H, false)}`;
    el.querySelector('svg').onclick = e => { const g = e.target.closest('.hm-c'); if (g) { e.preventDefault(); location.href = stockUrl(LAY.cells[+g.dataset.i].r.t); } };
    el.querySelector('svg').onmousemove = e => { const g = e.target.closest('.hm-c'); el.title = g ? `${LAY.cells[+g.dataset.i].r.t} ${LAY.cells[+g.dataset.i].r.ko || LAY.cells[+g.dataset.i].r.n || ''} ${label(val(LAY.cells[+g.dataset.i].r))}` : ''; };
  }
  function recolor() {   // 재생 중: 배치는 그대로 두고 색·숫자만
    const svg = box.querySelector('#hm svg'); if (!svg) return;
    svg.querySelectorAll('.hm-c').forEach(g => {
      const c = LAY.cells[+g.dataset.i], v = val(c.r);
      g.firstChild.setAttribute('fill', fill(v));
      const t = g.querySelector('.hm-v'); if (t) t.textContent = label(v);
    });
  }

  // ---- 재생
  const canPlay = () => !isSig() && COLOR[st.c].n && PX;
  function first() { return COLOR[st.c].cum ? 1 : COLOR[st.c].n; }
  function playBar() {
    if (isSig() || !COLOR[st.c].n) return `<div class="s13 mut hm-tl">${isSig() ? '신호 색은 지금 값만 보여요' : '올해 수익률은 재생 없이 지금 값만'}</div>`;
    if (!PX) return '<div class="s13 mut hm-tl">재생용 가격 불러오는 중…</div>';
    const n = PX.d.length, f0 = first();
    return `<div class="mx-tlbar hm-tl"><button class="btn" id="hm-play" aria-label="재생">${playing ? '❚❚' : '▶'}</button><span class="s13 mut">${esc(PX.d[COLOR[st.c].cum ? 0 : f0].slice(5).replace('-', '/'))}</span>
      <input type="range" id="hm-sl" min="${f0}" max="${n - 1}" step="0.02" value="${frame ?? n - 1}" aria-label="날짜 이동">
      <b class="s13" id="hm-d" style="min-width:86px;text-align:right">${frame == null ? '지금' : esc(PX.d[Math.round(frame)])}</b></div>
      <div class="small faint" style="padding:0 10px">${COLOR[st.c].cum ? `${esc(PX.d[0])}부터 그날까지 누적 변화` : `그날까지 ${COLOR[st.c].name} 변화`} · 크기는 지금 시가총액</div>`;
  }
  function setFrame(f) {
    const n = PX.d.length;
    frame = f >= n - 1 - 1e-6 ? null : f;
    const sl = box.querySelector('#hm-sl'), d = box.querySelector('#hm-d');
    if (sl && +sl.value !== f) sl.value = f;
    if (d) d.textContent = frame == null ? '지금' : PX.d[Math.round(f)];
    recolor();
  }
  function play() {
    if (playing) { playing = false; cancelAnimationFrame(raf); bindPlay(); return; }
    const n = PX.d.length, f0 = first();
    let f = frame == null || frame >= n - 1.01 ? f0 : frame, last = 0;
    playing = true; bindPlay();
    const step = ts => {
      if (!playing) return;
      if (last) f += (ts - last) / 1000 * Math.max(4, (n - f0) / 9);   // 전체를 약 9초에
      last = ts;
      if (f >= n - 1) { setFrame(n - 1); playing = false; bindPlay(); return; }
      setFrame(f); raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }
  function bindPlay() {
    const pb = box.querySelector('#hm-play'); if (pb) { pb.textContent = playing ? '❚❚' : '▶'; pb.onclick = play; }
    const sl = box.querySelector('#hm-sl'); if (sl) sl.oninput = e => { if (playing) { playing = false; cancelAnimationFrame(raf); pb && (pb.textContent = '▶'); } setFrame(+e.target.value); };
  }

  // ---- 화면
  function controls() {
    return `<div class="mx-ctl">
      <div class="mx-seg" role="tablist" aria-label="색 기준 — 주가"><span class="s13 mut" style="align-self:center;padding:0 4px 0 8px">주가</span>${Object.entries(COLOR).map(([k, c]) => `<button role="tab" class="${k === st.c ? 'on' : ''}" data-c="${k}">${c.name}</button>`).join('')}</div>
      <div class="mx-seg" role="tablist" aria-label="색 기준 — 신호"><span class="s13 mut" style="align-self:center;padding:0 4px 0 8px">신호</span>${Object.entries(SIG).map(([k, n]) => `<button role="tab" class="${k === st.c ? 'on' : ''}" data-c="${k}">${n}</button>`).join('')}</div>
      <label class="s13 mut">시가총액 <select class="f" id="hm-cap">${CAPS.map(([v, l]) => `<option value="${v}" ${v === st.cap ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      ${st.sec ? `<button class="btn" id="hm-all" style="min-height:34px">← 전체 업종</button><b>${esc(secKo(st.sec))}</b>` : '<span class="s13 mut">업종 이름을 누르면 그 업종만 크게</span>'}
    </div>`;
  }
  function legend() {
    const m = scale(), lab = isSig() ? ['신호 나빠짐', '신호 좋아짐'] : [`-${(m * 100).toFixed(0)}%`, `+${(m * 100).toFixed(0)}%`];
    const stops = [-1, -0.6, -0.3, -0.1, 0, 0.1, 0.3, 0.6, 1].map(k => `<i style="background:${fill(k * m)}"></i>`).join('');
    return `<div class="hm-leg"><span>${lab[0]}</span><span class="hm-sw">${stops}</span><span>${lab[1]}</span><span class="mut" style="margin-left:auto" id="hm-n"></span></div>`;
  }
  function render() {
    box.querySelector('#hm-ctl').innerHTML = controls();
    box.querySelector('#hm-top').innerHTML = playBar() + legend();
    draw(); bindPlay();
  }
  function bind() {
    box.querySelector('#hm-ctl').onclick = e => {
      const b = e.target.closest('[data-c]');
      if (b) { st.c = b.dataset.c; frame = null; playing = false; cancelAnimationFrame(raf); sync(); render(); return; }
      if (e.target.closest('#hm-all')) { st.sec = ''; sync(); render(); }
    };
    box.querySelector('#hm-ctl').onchange = e => { if (e.target.id === 'hm-cap') { st.cap = +e.target.value; sync(); render(); } };
    const el = box.querySelector('#hm'), tip = box.querySelector('#hm-tip');
    let lastPt = 'mouse', tapped = null;
    el.onpointerdown = e => { lastPt = e.pointerType; };
    el.onclick = e => {
      const s = e.target.closest('.hm-s'); const g = e.target.closest('.hm-c');
      if (g) {
        if (lastPt === 'touch' && tapped !== g.dataset.i) { tapped = g.dataset.i; el.onpointermove(e); return; }   // 휴대폰: 한 번 누르면 정보, 한 번 더 누르면 종목 화면
        location.href = stockUrl(LAY.cells[+g.dataset.i].r.t); return;
      }
      if (s && !st.sec) { st.sec = s.dataset.sec; sync(); render(); scrollTo({ top: box.offsetTop - 60, behavior: 'smooth' }); }
    };
    el.onpointermove = e => {
      const g = e.target.closest('.hm-c'), s = e.target.closest('.hm-s');
      if (!g) { if (s && !st.sec && s.querySelector('text')) { tip.innerHTML = `<b>${esc(secKo(s.dataset.sec))}</b> · 눌러서 크게 보기`; place(e); } else tip.style.display = 'none'; return; }
      const c = LAY.cells[+g.dataset.i], r = c.r, v = val(c.r);
      const cName = isSig() ? `${SIG[st.c]} 신호` : `${COLOR[st.c].name} 주가`;
      tip.innerHTML = `<b>${esc(r.t)}</b> ${esc(r.ko || r.n || '')}<br><span style="opacity:.75">${esc(c.ind)} · 시가총액 ${fmtUsd(r.mcap)}</span><br>${cName} <b>${label(v) || '-'}</b>${lastPt === 'touch' ? '<br><span style="opacity:.75">한 번 더 누르면 종목 화면</span>' : ''}${frame != null ? ` <span style="opacity:.75">(${esc(PX.d[Math.round(frame)])}까지)</span>` : ''}`;
      place(e);
    };
    el.onpointerleave = () => { tip.style.display = 'none'; };
    function place(e) {
      tip.style.display = 'block';
      const b = el.getBoundingClientRect(), w = tip.offsetWidth;
      let x = e.clientX - b.left + 14; if (x + w > b.width) x = e.clientX - b.left - w - 14;
      tip.style.left = Math.max(4, x) + 'px'; tip.style.top = (e.clientY - b.top + 14) + 'px';
    }
  }

  function mount(el, u) {
    U = u; S = U.rows.filter(r => r.k === 'stock' && r.mcap); box = el;
    box.innerHTML = `<div class="card" id="hm-ctl" style="gap:10px"></div>
      <div class="mx-chart hm-wrap"><div id="hm-top"></div><div id="hm"></div><div class="mx-tip" id="hm-tip"></div></div>`;
    bind(); render();
    if (ro) ro.disconnect();
    let t; ro = new ResizeObserver(() => { clearTimeout(t); t = setTimeout(() => { if (box.isConnected && box.querySelector('#hm')) draw(); }, 150); });
    ro.observe(box.querySelector('#hm'));
    if (!PX) Data.px3m().then(j => { PX = j; if (box.isConnected && box.querySelector('#hm-top')) { box.querySelector('#hm-top').innerHTML = playBar() + legend(); bindPlay(); box.querySelector('#hm-n').textContent = `${LAY.cells.length}종목`; } }).catch(() => { });
  }
  function unmount() { playing = false; cancelAnimationFrame(raf); if (ro) ro.disconnect(); ro = null; frame = null; }
  return { mount, unmount, mini };
})();
