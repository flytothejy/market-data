/* 여러 칸(가격 + 보조지표) 차트를 세로로 쌓고 시간축·십자선을 동기화 — TradingView Lightweight Charts v4
   buildStack(el, {dates, panes:[{title, height, series:[...], lines:[{value,label}], markers:[...]}], defaultRange:'1Y'})
   series: {type:'candle', o,h,l,c, up, down} | {type:'line', v, color, width, name} | {type:'hist', v, colorFn, name} */
(function () {
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const C = dark
    ? { fg: '#ecebe6', mut: '#9b9a94', grid: '#262624', bg: '#1d1d1b', acc: '#fb923c', blue: '#60a5fa', red: '#f87171', green: '#4ade80', gray: '#6b6b66' }
    : { fg: '#1d1d1b', mut: '#6b6b66', grid: '#efeee9', bg: '#ffffff', acc: '#c2410c', blue: '#2563eb', red: '#dc2626', green: '#16a34a', gray: '#a8a8a2' };
  window.CHART_COLORS = C;
  const fmt = (v, d) => (v == null || isNaN(v) ? '—' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: d }));

  window.buildStack = function (root, cfg) {
    const LW = window.LightweightCharts;
    const dates = cfg.dates;
    const charts = [], mains = [], valueAt = [];
    // 기간 버튼
    const bar = document.createElement('div'); bar.className = 'rng';
    const ranges = [['3M', 3], ['6M', 6], ['1Y', 12], ['3Y', 36], ['전체', 0]];
    root.appendChild(bar);
    cfg.panes.forEach((p, pi) => {
      const wrap = document.createElement('div'); wrap.className = 'pane'; wrap.style.height = p.height + 'px';
      const leg = document.createElement('div'); leg.className = 'leg'; wrap.appendChild(leg);
      root.appendChild(wrap);
      const last = pi === cfg.panes.length - 1; if (pi === 0) wrap.style.borderTop = '0';
      const ch = LW.createChart(wrap, {
        autoSize: true,
        layout: { attributionLogo: false, background: { color: 'transparent' }, textColor: C.mut, fontSize: 11, fontFamily: '-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif' },
        grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
        rightPriceScale: { borderVisible: false, minimumWidth: 64, scaleMargins: p.margins || { top: 0.12, bottom: 0.08 } },
        timeScale: { borderVisible: false, visible: last, rightOffset: 3, fixLeftEdge: true },
        crosshair: { mode: LW.CrosshairMode.Normal, vertLine: { color: C.mut, labelVisible: last }, horzLine: { color: C.mut } },
        handleScroll: { vertTouchDrag: false },   // 모바일에서 세로 스크롤은 페이지로
        localization: { locale: 'ko-KR', dateFormat: 'yyyy-MM-dd' },
      });
      const vals = {};
      const pf = d => ({ type: 'price', precision: d, minMove: Math.pow(10, -d) });
      let mainS = null; const named = [];
      p.series.forEach((s, si) => {
        let sr;
        if (s.type === 'candle') {
          sr = ch.addCandlestickSeries({ upColor: s.up, downColor: s.down, borderUpColor: s.up, borderDownColor: s.down, wickUpColor: s.up, wickDownColor: s.down, priceLineVisible: false, priceFormat: pf(s.digits ?? 2) });
          sr.setData(dates.map((d, i) => s.c[i] == null ? null : { time: d, open: s.o[i], high: s.h[i], low: s.l[i], close: s.c[i] }).filter(Boolean));
          dates.forEach((d, i) => { vals[d] = vals[d] || {}; vals[d][si] = s.c[i]; });
          named.push([si, p.title, s.digits ?? 2]);
        } else if (s.type === 'line') {
          sr = ch.addLineSeries({ color: s.color || C.fg, lineWidth: s.width || 1.5, priceLineVisible: false, lastValueVisible: s.lastValue ?? true, crosshairMarkerRadius: 3, priceFormat: pf(s.digits ?? 2) });
          sr.setData(dates.map((d, i) => s.v[i] == null ? null : { time: d, value: s.v[i] }).filter(Boolean));
          dates.forEach((d, i) => { vals[d] = vals[d] || {}; vals[d][si] = s.v[i]; });
          named.push([si, s.name || p.title, s.digits ?? 2]);
        } else {
          sr = ch.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false, base: 0, priceFormat: pf(s.digits ?? 2) });
          sr.setData(dates.map((d, i) => s.v[i] == null ? null : { time: d, value: s.v[i], color: s.colorFn(s.v[i]) }).filter(Boolean));
          dates.forEach((d, i) => { vals[d] = vals[d] || {}; vals[d][si] = s.v[i]; });
          named.push([si, s.name || p.title, s.digits ?? 2]);
        }
        if (si === 0) mainS = sr;
      });
      (p.lines || []).forEach(l => mainS.createPriceLine({ price: l.value, color: C.acc, lineWidth: 1, lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title: '' }));
      if (p.markers && p.markers.length) mainS.setMarkers(p.markers.slice().sort((a, b) => a.time < b.time ? -1 : 1));
      const setLeg = d => {
        const v = vals[d] || {};
        leg.innerHTML = named.map(([si, nm, dg], k) => `<span${k ? '' : ' class="t"'}>${nm} <b>${fmt(v[si], dg)}</b></span>`).join('') + (p.note ? `<span class="nt">${p.note}</span>` : '');
      };
      setLeg(dates[dates.length - 1]);
      charts.push(ch); mains.push(mainS); valueAt.push(d => (vals[d] || {})[0]); ch._setLeg = setLeg;
    });
    // 시간축 동기화
    let lock = false;
    charts.forEach((ch, i) => ch.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (lock || !r) return; lock = true;
      charts.forEach((o, j) => { if (j !== i) o.timeScale().setVisibleLogicalRange(r); });
      lock = false;
    }));
    // 십자선 동기화 + 범례 값
    charts.forEach((ch, i) => ch.subscribeCrosshairMove(prm => {
      if (lock) return; lock = true;
      const t = prm && prm.time;
      charts.forEach((o, j) => {
        if (t) { o._setLeg(t); if (j !== i) { const v = valueAt[j](t); if (v != null) o.setCrosshairPosition(v, t, mains[j]); } }
        else { o._setLeg(dates[dates.length - 1]); if (j !== i) o.clearCrosshairPosition(); }
      });
      lock = false;
    }));
    // 기간 버튼
    const setRange = m => {
      const end = dates[dates.length - 1];
      if (!m) { charts[0].timeScale().fitContent(); return; }
      const s = new Date(end); s.setMonth(s.getMonth() - m);
      charts[0].timeScale().setVisibleRange({ from: s.toISOString().slice(0, 10), to: end });
    };
    ranges.forEach(([lab, m]) => {
      const b = document.createElement('button'); b.textContent = lab;
      b.onclick = () => { bar.querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); setRange(m); };
      if (lab === (cfg.defaultRange || '1Y')) b.classList.add('on');
      bar.appendChild(b);
    });
    requestAnimationFrame(() => setRange((ranges.find(r => r[0] === (cfg.defaultRange || '1Y')) || [0, 12])[1]));
    return charts;
  };

  window.CHART_CSS = `
  .rng{display:flex;gap:6px;margin:4px 0 8px}
  .rng button{font:inherit;font-size:12px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);background:transparent;color:var(--mut);cursor:pointer}
  .rng button.on{border-color:var(--acc);color:var(--acc);font-weight:650}
  .pane{position:relative;border-top:1px solid var(--line)}
  .pane:first-of-type{border-top:0}
  .leg{position:absolute;left:4px;top:3px;z-index:3;font-size:11.5px;color:var(--mut);pointer-events:none;display:flex;flex-wrap:wrap;gap:2px 10px;max-width:calc(100% - 80px)}
  .leg b{color:var(--fg);font-weight:600} .leg .t{color:var(--fg);font-weight:650} .leg .nt{color:var(--acc)}`;
  const st = document.createElement('style'); st.textContent = window.CHART_CSS; document.head.appendChild(st);
})();
