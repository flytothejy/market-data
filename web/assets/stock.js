// stock.html 화면 (정적 페이지 /hub/s/·/hub/i/ 에서도 같이 씀)
header('종목');
const T = (window.HUB_T || qs('t') || '').toUpperCase();
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// ---- 가격 차트 (일봉 2년 / 주간 종가 20년)
function priceChart(el, d, isEtf) {
  const chart = LightweightCharts.createChart(el, {
    autoSize: true, layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontSize: 11 },
    grid: { vertLines: { visible: false }, horzLines: { color: css('--line2') } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, crosshair: { mode: 0 },
    localization: { locale: 'ko-KR' },
  });
  const up = css('--up'), dn = css('--dn');
  let main, vol;
  const daily = n => {
    if (main) chart.removeSeries(main); if (vol) chart.removeSeries(vol);
    const cut = d.px.d.length - n;
    if (d.px.o) {
      main = chart.addCandlestickSeries({ upColor: up, downColor: dn, borderVisible: false, wickUpColor: up, wickDownColor: dn });
      main.setData(d.px.d.map((t, i) => ({ time: t, open: d.px.o[i], high: d.px.h[i], low: d.px.l[i], close: d.px.c[i] })).slice(Math.max(0, cut)));
    } else {
      main = chart.addLineSeries({ color: up, lineWidth: 2 });
      main.setData(d.px.d.map((t, i) => ({ time: t, value: d.px.c[i] })).slice(Math.max(0, cut)));
    }
    vol = chart.addHistogramSeries({ priceScaleId: 'v', priceFormat: { type: 'volume' }, color: css('--line') });
    chart.priceScale('v').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(d.px.d.map((t, i) => ({ time: t, value: d.px.v[i] })).slice(Math.max(0, cut)));
    chart.timeScale().fitContent();
  };
  const weekly = years => {
    if (main) chart.removeSeries(main); if (vol) chart.removeSeries(vol); vol = null;
    const from = new Date(Date.now() - years * 365.25 * 864e5).toISOString().slice(0, 10);
    main = chart.addAreaSeries({ lineColor: up, topColor: up + '33', bottomColor: up + '00', lineWidth: 2 });
    main.setData(d.wk.d.map((t, i) => ({ time: t, value: d.wk.c[i] })).filter(x => x.time >= from));
    chart.timeScale().fitContent();
  };
  return { '3개월': () => daily(63), '6개월': () => daily(126), '1년': () => daily(252), '2년': () => daily(9999), '10년': () => weekly(10), '전체': () => weekly(30) };
}

function miniLine(el, dates, vals, color, fmtFn) {
  const c = LightweightCharts.createChart(el, {
    autoSize: true, layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontSize: 11 },
    grid: { vertLines: { visible: false }, horzLines: { color: css('--line2') } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, handleScroll: false, handleScale: false, localization: { locale: 'ko-KR' },
  });
  const s = c.addLineSeries({ color, lineWidth: 2, priceFormat: { type: 'custom', formatter: fmtFn } });
  s.setData(dates.map((t, i) => ({ time: t, value: vals[i] })).filter(x => x.value != null));
  c.timeScale().fitContent();
}

// 재무 막대 (SVG)
function bars(rows, keys, labels, colors) {
  const W = 100 / rows.length;
  const max = Math.max(...rows.flatMap(r => keys.map(k => Math.abs(r[k] || 0)))) || 1;
  const anyNeg = rows.some(r => keys.some(k => (r[k] || 0) < 0));
  const base = anyNeg ? 70 : 100;
  return `<div style="display:flex;gap:12px;font-size:12px;color:var(--muted)">${keys.map((k, i) => `<span><span class="cat-dot" style="background:${colors[i]}"></span>${labels[i]}</span>`).join('')}</div>
  <svg viewBox="0 0 100 ${anyNeg ? 100 : 100}" preserveAspectRatio="none" style="width:100%;height:160px">
    ${rows.map((r, j) => keys.map((k, i) => {
      const v = r[k] || 0, h = Math.abs(v) / max * (anyNeg ? 68 : 96), bw = W * 0.7 / keys.length, x = j * W + W * 0.15 + i * bw;
      return `<rect x="${x}" y="${v >= 0 ? base - h : base}" width="${bw * 0.9}" height="${h}" fill="${colors[i]}" rx="0.4"><title>${fmtUsd(v)}</title></rect>`;
    }).join('')).join('')}
    <line x1="0" x2="100" y1="${base}" y2="${base}" stroke="var(--line)" stroke-width="0.3"/>
  </svg>
  <div style="display:flex;font-size:11px;color:var(--faint)">${rows.map(r => `<span style="width:${W}%;text-align:center">${r.end.slice(2, 7).replace('-', '.')}</span>`).join('')}</div>`;
}

function kvGrid(m, keys, F) {
  return `<div class="kv">${keys.filter(k => F[k]).map(k => {
    const f = F[k]; let v = m[k];
    let txt = f.fmt === 'pct' && ['r1d', 'r1w', 'r1m', 'r3m', 'r6m', 'r1y', 'rytd', 'r12_1', 'd50', 'd200', 'hi52', 'lo52', 'rev_g', 'rev_qg', 'ni_g', 'c_chg90', 'c_upside', 'c_eps_g', 'c_rev_g', 'c_surp', 'c_ratio'].includes(k) ? pctS(v)
      : k === 'om_chg' || k === 'sv_chg' ? (v == null ? '-' : `<span class="${cls(v)}">${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%p</span>`) : fmt(v, f.fmt);
    if (f.tier === 'pro' && !Plan.isPro()) txt = '<span class="pro">PRO</span>';
    return `<div><span>${esc(f.label)}${tip(k)}</span><b>${txt}</b></div>`;
  }).join('')}</div>`;
}

const sec = (id, key, title, desc, body) => `<section id="${id}" style="display:flex;flex-direction:column;gap:12px;scroll-margin-top:110px">
  <div class="sec-head"><h2>${key ? `<span class="cat-dot c-${key}"></span>` : ''}${title}</h2><span class="desc">${desc}</span></div>${body}</section>`;
const card = (title, sub, body, extra = '') => `<div class="card" ${extra}>${title ? `<h3>${title}</h3>` : ''}${sub ? `<div class="sub">${sub}</div>` : ''}${body}</div>`;

function chartCard(id) {
  return `<div class="card"><div class="seg" id="${id}-seg"></div><div class="chart" id="${id}"></div></div>`;
}
function mountChart(id, d, isEtf) {
  const modes = priceChart($('#' + id), d, isEtf), seg = $('#' + id + '-seg');
  Object.keys(modes).forEach(k => { if (k.endsWith('년') && !d.wk && k !== '1년' && k !== '2년') return;
    const b = document.createElement('button'); b.className = 'btn'; b.textContent = k;
    b.onclick = () => { seg.querySelectorAll('.btn').forEach(x => x.classList.remove('on')); b.classList.add('on'); modes[k](); };
    seg.append(b); if (k === '1년') b.click(); });
}

function headBlock(m, extraTags) {
  const tags = [m.sec ? secKo(m.sec) : null, m.ind, ...(m.idx ? m.idx.split(',') : []), ...extraTags].filter(Boolean);
  return `<div class="hero"><div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><h1>${esc(m.t)}</h1><span class="mut" style="font-size:17px">${m.ko ? `<b style="color:var(--ink);font-weight:650">${esc(m.ko)}</b> · ` : ''}${esc(m.n)}</span></div>
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><b style="font-size:28px" class="num">${fmt(m.px, 'px')}</b>${pctS(m.r1d)}
    <span class="mut s13">${m.mcap ? '시가총액 ' + fmtUsd(m.mcap) : m.aum ? '순자산 ' + fmtUsd(m.aum) : ''}</span></div>
    <div class="pill-row" style="align-items:center">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}
      <span style="margin-left:auto;display:flex;gap:6px">${watchBtn(m.t)}<a class="btn" href="compare.html?t=${encodeURIComponent([m.t, ...Watch.list().filter(x => x !== m.t)].slice(0, 3).join(','))}" style="text-decoration:none">비교하기</a></span></div>
    ${m.s1 ? `<p style="margin:6px 0 0;font-size:15px;color:var(--ink)">${esc(m.s1)}</p>` : ''}</div>`;
}

// ================================================================ 종목
async function renderStock(U, d, P) {
  const isPro = !!P;
  const F = U.fields, m = d.m;
  const tabs = [['ov', '개요'], ['cons', '컨센서스'], ['fin', '재무'], ['tech', '차트·수급'], ['doc', '공시·내부자'], ['news', '뉴스']];
  let h = headBlock(m, []);
  h += `<nav class="tabs">${tabs.map(([k, l], i) => `<a href="#${k}" class="${i ? '' : 'on'}">${l}</a>`).join('')}</nav>`;

  // 다섯 카테고리 요약
  const pick = (k) => m[k];
  h += `<div class="grid g4" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">
    ${[['cons', '컨센서스', m.c_n ? `순상향률 ${fmt(m.c_ratio, 'pct', { sign: true })}` : '준비 중', m.c_next ? `다음 실적 ${m.c_next}` : m.c_n ? `애널리스트 ${m.c_n}명` : 'S&P 500부터 제공'],
       ['fin', '재무', `매출 성장 ${fmt(m.rev_g, 'pct', { sign: true })}`, `영업이익률 ${fmt(m.om, 'pct')} · PER ${fmt(m.pe, 'x')}`],
       ['tech', '차트·수급', `1년 ${fmt(m.r1y, 'pct', { sign: true })}`, `200일선 대비 ${fmt(m.d200, 'pct', { sign: true })} · 공매도 ${fmt(m.sv, 'pct')}`],
       ['doc', '공시·내부자', `내부자 매수 ${fmtUsd(m.ib || 0)}`, m.k8_last ? `최근 8-K ${m.k8_last}` : `매도 ${fmtUsd(m.is || 0)}`],
       ['news', '뉴스', `7일 ${m.nw7 || 0}건`, m.nw_last ? esc(m.nw_last.slice(0, 40)) + '…' : '']]
      .map(([k, l, a, b]) => `<a class="card" href="#${k}" style="color:inherit;text-decoration:none;gap:2px"><span class="small mut"><span class="cat-dot c-${k}"></span>${l}</span><b>${a}</b><span class="small mut" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${b}</span></a>`).join('')}
  </div>`;

  // 개요 + 차트
  h += sec('ov', '', '개요', `${esc(d.asof || '')} 종가 기준`, chartCard('pc') +
    (d.summary ? card('회사 소개', `${d.web ? `<a href="${esc(d.web)}" target="_blank" rel="noopener">${esc(d.web.replace(/^https?:\/\//, ''))}</a>` : ''}${d.emp ? ` · 직원 ${Math.round(d.emp).toLocaleString()}명` : ''}`, `<p class="clamp" onclick="this.classList.toggle('open')" style="margin:0;font-size:14px;color:var(--muted)">${esc(d.summary)}</p>`) : ''));

  // 실적 발표
  const er = d.er || {};
  let erCard = '';
  if (er.next || (er.hist && er.hist.length)) {
    const hist = (er.hist || []).slice(-8);
    const mx = Math.max(0.05, ...hist.map(x => Math.abs(x[1])));
    const bars8 = hist.length ? `<div style="display:flex;align-items:center;gap:4px;height:120px;position:relative;border-bottom:0">
        ${hist.map(([dd, v]) => `<div style="flex:1;display:flex;flex-direction:column;justify-content:center;height:100%" title="${dd} ${fmt(v, 'pct', { sign: true })}">
          <div style="height:50%;display:flex;align-items:flex-end">${v > 0 ? `<i style="display:block;width:100%;height:${v / mx * 100}%;background:var(--up);border-radius:3px 3px 0 0"></i>` : ''}</div>
          <div style="height:50%;display:flex;align-items:flex-start;border-top:1px solid var(--line)">${v < 0 ? `<i style="display:block;width:100%;height:${-v / mx * 100}%;background:var(--dn);border-radius:0 0 3px 3px"></i>` : ''}</div></div>`).join('')}</div>
      <div style="display:flex;gap:4px;font-size:11px;color:var(--faint)">${hist.map(([dd, v]) => `<span style="flex:1;text-align:center"><span class="${cls(v)}">${fmt(v, 'pct', { sign: true })}</span><br>${dd.slice(2, 7).replace('-', '.')}</span>`).join('')}</div>` : '';
    const ratio = er.imp && er.avg ? er.imp / er.avg : null;
    const verdict = ratio == null ? '' : ratio > 1.5 ? '옵션 시장은 이번 발표에서 평소보다 큰 움직임을 예상하고 있어요' : ratio < 0.8 ? '옵션 시장은 이번 발표에서 평소보다 작은 움직임을 예상하고 있어요' : '옵션 시장의 예상은 과거 평균과 비슷한 수준이에요';
    erCard = card('실적 발표', '과거 발표 때 주가 반응과 옵션 시장이 예상하는 이번 변동폭',
      `<div class="kv"><div><span>다음 발표${tip('c_next')}</span><b>${er.next ? esc(er.next) : '-'}</b>${er.when || er.est ? `<span>${er.when ? er.when + ' 발표' : ''}${er.est ? '예상일' : ''}</span>` : ''}</div>
        <div><span>옵션 예상 변동폭${tip('er_imp')}</span><b>${er.imp != null ? '±' + fmt(er.imp, 'pct') : '-'}</b></div>
        <div><span>과거 평균 변동${tip('er_avg')}</span><b>${er.avg != null ? '±' + fmt(er.avg, 'pct') : '-'}</b></div>
        <div><span>최근 서프라이즈${tip('c_surp')}</span><b>${pctS(m.c_surp)}</b></div></div>
      ${verdict ? `<div class="s13">${verdict}${er.exp ? ` <span class="faint">(만기 ${esc(er.exp)} 옵션 기준)</span>` : ''}</div>` : er.next && er.imp == null ? '<div class="small faint">옵션 예상 변동폭은 옵션을 수집하는 시가총액 상위 종목만, 발표 직후 끝나는 만기가 생기면(보통 발표 주간) 보여요</div>' : ''}
      ${hist.length ? `<div class="small mut">최근 ${hist.length}번의 실적 발표 때 주가 변동 (발표 전날 → 다음 날 종가)</div>${bars8}` : ''}`);
  }

  // 컨센서스
  const consKeys = ['c_n', 'c_up', 'c_dn', 'c_ratio', 'c_chg90', 'c_eps_g', 'c_rev_g', 'c_fpe', 'c_upside', 'c_buy', 'c_surp', 'c_beats', 'c_next'];
  const fakeHist = `<div style="height:140px;background:linear-gradient(180deg,transparent 40%,var(--soft));border-radius:10px"></div>`;
  h += sec('cons', 'cons', '컨센서스', '애널리스트 전망과 그 변화',
    erCard + (m.c_n ? card('', '', kvGrid(m, consKeys, F)) : card('', '', `<div class="mut s13">이 종목의 컨센서스는 준비 중입니다. 지금은 S&P 500 종목부터 제공하고 있어요.${m.c_next ? ` 다음 실적 발표 예정일: <b>${m.c_next}</b>` : ''}</div>`)) +
    card('전망치 일별 이력 <span class="pro">PRO</span>', '내년 EPS 전망과 30일 상향·하향 건수를 날마다 쌓은 기록',
      !isPro ? lockBox(fakeHist, '전망치가 언제, 얼마나 바뀌었는지 일별로 볼 수 있어요')
        : P.cons_hist ? `<div class="small mut">내년 EPS 전망 ($)</div><div class="chart sm" id="ch-eps"></div><div class="small mut">30일 상향(위) · 하향(아래) 건수</div><div class="chart sm" id="ch-rev" style="height:130px"></div>
          <div class="small faint">${P.cons_hist.d.length}일째 쌓는 중 (${esc(P.cons_hist.d[0])}부터) — 날마다 한 점씩 늘어납니다</div>`
        : '<div class="mut s13">이 종목의 전망 이력이 아직 없습니다</div>'));

  // 재무
  const fin = d.fin || {};
  let finBody = '';
  if (fin.annual && fin.annual.length) {
    finBody += `<div class="card"><div class="seg" id="fin-seg"><button class="btn on" data-k="annual">연간 (최근 5년)</button><button class="btn" data-k="quarterly">분기 (최근 12분기)</button>
      ${isPro && P.fin_annual_full ? '<button class="btn" data-k="full">15년 <span class="pro">PRO</span></button>' : '<button class="btn" disabled title="프로 멤버십">15년 <span class="pro">PRO</span></button>'}</div><div id="fin-box"></div></div>`;
    if (isPro && P.fin_annual_full) fin.full = P.fin_annual_full;
  }
  finBody += card('', `최근 4개 분기 합계 · 기준일 ${fmt(m.fq, 'date')}${m.cur && m.cur !== 'USD' ? ` · 재무 통화 ${esc(m.cur)} (밸류에이션 지표 제외)` : ''}`,
    kvGrid(m, ['rev', 'rev_g', 'rev_qg', 'gm', 'om', 'om_chg', 'nm', 'ni', 'ni_g', 'eps', 'fcf', 'roe', 'roa', 'de', 'cr', 'rnd', 'pe', 'ps', 'pb', 'fcfy', 'dy', 'shy'], F));
  h += sec('fin', 'fin', '재무', 'SEC에 제출한 재무제표(XBRL) 기준', finBody);

  // 차트·수급
  let techBody = card('', '', kvGrid(m, ['r1w', 'r1m', 'r3m', 'r6m', 'r1y', 'rytd', 'r12_1', 'd50', 'd200', 'rsi', 'hi52', 'lo52', 'vr', 'vol', 'gc', 'sv', 'sv_chg', 'si', 'iv', 'pcr', 'skew'], F));
  techBody += `<div class="grid g2">${card('공매도 거래 비중', 'FINRA 일별 공매도 거래량 / 전체 거래량 (최근 120거래일)', d.short ? '<div class="chart sm" id="sv-c"></div>' : '<div class="mut s13">자료 없음</div>')}
    ${card('내재변동성 (30일 등가격)', '옵션 가격이 말하는 앞으로의 연간 변동성', d.opt && d.opt.d.length > 1 ? '<div class="chart sm" id="iv-c"></div>' : d.opt ? `<div style="font-size:22px;font-weight:700">${fmt(d.opt.iv[0], 'pct')}</div><div class="mut s13">쌓이는 중 — 매일 한 점씩 추가됩니다</div>` : '<div class="mut s13">시가총액 상위 200개 종목만 수집합니다</div>')}</div>`;
  const etfIn = d.etf_in || [];
  techBody += `<div class="grid g2">${card(`이 종목을 담은 ETF <span class="faint small">${etfIn.length}개</span>`, '추적 ETF 159개 중 비중 순', etfIn.length ? `<div class="rank">${etfIn.slice(0, 10).map(([e, w], i) => `<a class="r" href="${stockUrl(e)}"><span class="i">${i + 1}</span><span class="nm"><b>${e}</b></span><span class="v num">${(+w).toFixed(2)}%</span></a>`).join('')}</div>` : '<div class="mut s13">추적 ETF에 편입되어 있지 않습니다</div>')}
    ${card('유명 투자자·기관 보유 (13F) <a class="small" href="investors.html" style="font-weight:400">전체 →</a>', d.g13 ? `분기 말 기준 · 분기 종료 후 45일 안에 공개 · 포트폴리오 비중 = 그 기관 전체 보유액 중 이 종목` : '', d.g13 ? `<div class="tbl-wrap" style="max-height:420px;overflow-y:auto"><table class="t"><thead><tr><th>투자자</th><th>기준</th><th>평가액</th><th>포트폴리오 비중</th><th>주식 수 변화</th></tr></thead><tbody>${d.g13.holders.map(x => `<tr><td class="nm">${esc(x.m)}${x.k !== 'guru' ? ` <span class="tag">${x.k === 'fund' ? '헤지펀드·퀀트' : '대형 운용사'}</span>` : ''}</td><td class="mut">${esc((x.p || '').slice(2, 7).replace('-', '.'))}</td><td class="num">${fmtUsd(x.v)}</td><td class="num">${x.w != null ? (x.w * 100).toFixed(x.w < 0.01 ? 2 : 1) + '%' : '-'}</td><td>${x.new ? '<span class="up">신규</span>' : pctS(x.chg)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="mut s13">추적 중인 유명 투자자·기관이 보유하지 않았습니다</div>')}</div>`;
  h += sec('tech', 'tech', '차트·수급', '가격·거래량·공매도·옵션·기관 보유', techBody);

  // 공시·내부자
  let docBody = card('', '', kvGrid(m, ['ib', 'is', 'ibn', 'ib_last', 'k8', 'k8_last', 'k10', 'f144', 'g13d', 'rf_new', 'rf_sim', 'md_unc'], F));
  const codeKo = { P: '장내 매수', S: '장내 매도', A: '보상 취득', M: '옵션 행사', F: '세금 납부', G: '증여', D: '회사에 처분', C: '전환', X: '옵션 행사' };
  const ins = d.insider || [];
  docBody += card('내부자 거래', 'Form 4 · 최근 40건 · 10b5-1 = 미리 정해둔 매매 계획에 따른 거래', ins.length ? `<div class="tbl-wrap"><table class="t"><thead><tr><th>거래일</th><th class="l">이름</th><th class="l">직위</th><th class="l">구분</th><th>주식 수</th><th>가격</th><th>금액</th></tr></thead><tbody>
    ${ins.map(x => `<tr><td>${fmt(x.d, 'date')}</td><td class="l nm">${esc(x.who)}</td><td class="l nm mut">${esc(x.title)}</td><td class="l"><span class="${x.code === 'P' ? 'up' : x.code === 'S' ? 'dn' : 'mut'}">${codeKo[x.code] || x.code}</span>${x.plan ? ' <span class="tag">10b5-1</span>' : ''}</td>
      <td class="num">${fmt(x.sh, 'int')}</td><td class="num">${x.px ? fmt(x.px, 'px') : '-'}</td><td class="num">${x.v ? fmtUsd(x.v) : '-'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="mut s13">최근 내부자 거래가 없습니다</div>');
  const formKo = { '10-K': '연간 보고서', '10-Q': '분기 보고서', '8-K': '수시 공시', '144': '매도 예정 신고', 'DEF 14A': '주총 안내', 'SC 13G': '대주주 지분', 'SC 13D': '대주주 지분(경영 참여)', '20-F': '연간 보고서(해외)', '6-K': '수시 공시(해외)', 'S-8': '임직원 주식 등록', '424B2': '증권 발행' };
  docBody += card('공시 목록', 'SEC EDGAR · 최근 40건 (내부자 거래 제외)', (d.filings || []).length ? `<div class="tbl-wrap"><table class="t"><thead><tr><th>제출일</th><th class="l">양식</th><th class="l">내용</th></tr></thead><tbody>
    ${d.filings.map(x => `<tr><td>${fmt(x.d, 'date')}</td><td class="l"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.f)}</a></td><td class="l nm mut">${esc(x.items || formKo[x.f] || '')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="mut s13">공시 없음</div>');
  const TK = (d.tenk || []).slice().reverse();
  const tkTable = TK.length ? `<div class="tbl-wrap"><table class="t"><thead><tr><th>10-K 제출일</th><th>비교 대상</th><th>새 위험 문장 비율</th><th>위험요인 유사도</th><th>경영진 논의 유사도</th><th>불확실성 단어</th></tr></thead><tbody>
    ${TK.map(x => `<tr><td>${fmt(x.filed, 'date')}</td><td class="mut">${x.prev_filed ? fmt(x.prev_filed, 'date') : '-'}</td><td class="num">${fmt(x.rf_new, 'pct')}</td><td class="num">${x.sim_rf != null ? x.sim_rf.toFixed(3) : '-'}</td><td class="num">${x.sim_md != null ? x.sim_md.toFixed(3) : '-'}</td><td class="num">${x.md_unc != null ? (x.md_unc * 100).toFixed(2) + '%' : '-'}</td></tr>`).join('')}</tbody></table></div>
    <div class="small faint">새 위험 문장 비율 = 올해 위험요인 문장 중 작년 어떤 문장과도 닮지 않은 문장의 비율 · 유사도 1 = 작년과 같음</div>` : '<div class="mut s13">10-K 분석 결과가 없습니다 (해외 기업의 20-F 제출, 최근 상장 등)</div>';
  const NS = isPro && P.tenk_new ? P.tenk_new : null;
  const nsBody = !TK.length ? '' : NS ? `<div class="small mut">${esc(NS.filed)} 10-K에 새로 들어온 위험 문장 ${NS.sentences.length}개 (긴 순, 영문 원문)</div>
      <ol style="margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px;font-size:13.5px;line-height:1.55" id="ns-list">${NS.sentences.map((x, i) => `<li ${i >= 8 ? 'class="more" style="display:none"' : ''}>${esc(x)}</li>`).join('')}</ol>
      ${NS.sentences.length > 8 ? '<button class="btn" id="ns-more">전체 보기</button>' : ''}`
    : isPro ? '<div class="mut s13">새 위험 문장 원문이 아직 없습니다</div>'
    : lockBox(`<div style="display:flex;flex-direction:column;gap:6px">${Array(4).fill('<div style="height:14px;background:var(--soft);border-radius:4px"></div>').join('')}</div>`, '새로 들어온 위험 문장 원문을 볼 수 있어요');
  docBody += card('10-K 변화', '해마다 내는 연간 보고서(10-K)의 위험요인·경영진 논의를 작년 것과 비교', tkTable + (nsBody ? `<div style="border-top:1px solid var(--line2);padding-top:10px;display:flex;flex-direction:column;gap:8px"><b style="font-size:14px">새로 들어온 위험 문장 <span class="pro">PRO</span></b>${nsBody}</div>` : ''));
  h += sec('doc', 'doc', '공시·내부자', 'SEC EDGAR 제출 원문 기준', docBody);

  // 뉴스
  const nws = d.news || [];
  h += sec('news', 'news', '뉴스', '최근 기사·보도자료 (영문 원문)', card('', '', nws.length ? nws.map(x => `<div class="news-i"><a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a><span class="m">${fmt(x.d, 'date')} · ${esc(x.s || '')}${x.k === 'pr' ? ' · 보도자료' : ''}</span></div>`).join('') : '<div class="mut s13">최근 뉴스가 없습니다</div>'));

  $('#app').innerHTML = h;
  document.title = `${m.ko ? `${m.ko}(${m.t})` : `${m.n} (${m.t})`} 주가·실적 발표일·컨센서스 | 티커맵`;
  mountChart('pc', d, false);
  if (d.short) miniLine($('#sv-c'), d.short.d, d.short.r, css('--dn'), v => (v * 100).toFixed(0) + '%');
  if (d.opt && d.opt.d.length > 1) miniLine($('#iv-c'), d.opt.d, d.opt.iv, css('--up'), v => (v * 100).toFixed(0) + '%');
  if (fin.annual && fin.annual.length) {
    const draw = k => {
      const rows = fin[k] || [];
      const tbl = `<div class="tbl-wrap"><table class="t"><thead><tr><th>기준일</th>${rows.map(r => `<th>${r.end.slice(0, 7)}</th>`).join('')}</tr></thead><tbody>
        ${[['매출', r => fmtUsd(r.rev)], ['매출총이익률', r => fmt(r.gp != null && r.rev ? r.gp / r.rev : null, 'pct')], ['영업이익', r => fmtUsd(r.opi)], ['영업이익률', r => fmt(r.opi != null && r.rev ? r.opi / r.rev : null, 'pct')],
           ['순이익', r => fmtUsd(r.ni)], ['EPS', r => r.eps != null ? '$' + r.eps.toFixed(2) : '-'], ['영업현금흐름', r => fmtUsd(r.cfo)], ['설비투자', r => fmtUsd(r.capex)],
           ['연구개발비', r => fmtUsd(r.rnd)], ['자사주 매입', r => fmtUsd(r.buyback)], ['배당 지급', r => fmtUsd(r.divpaid)]]
          .map(([l, f]) => `<tr><td>${l}</td>${rows.map(r => `<td class="num">${f(r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      $('#fin-box').innerHTML = (rows.length ? bars(rows, ['rev', 'ni'], ['매출', '순이익'], [css('--line'), css('--accent')]) : '') + tbl;
    };
    $('#fin-seg').querySelectorAll('.btn[data-k]').forEach(b => b.onclick = () => { $('#fin-seg').querySelectorAll('.btn').forEach(x => x.classList.remove('on')); b.classList.add('on'); draw(b.dataset.k); });
    draw('annual');
  }
  if (isPro && P.cons_hist) {
    const h2 = P.cons_hist;
    miniLine($('#ch-eps'), h2.d, h2.eps1y, css('--accent'), v => '$' + v.toFixed(2));
    const c = LightweightCharts.createChart($('#ch-rev'), { autoSize: true, layout: { background: { color: 'transparent' }, textColor: css('--muted'), fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: css('--line2') } }, rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false },
      handleScroll: false, handleScale: false, localization: { locale: 'ko-KR' } });
    const up = c.addHistogramSeries({ color: css('--up'), priceFormat: { type: 'custom', formatter: v => Math.abs(v).toFixed(0) } });
    const dn = c.addHistogramSeries({ color: css('--dn'), priceFormat: { type: 'custom', formatter: v => Math.abs(v).toFixed(0) } });
    up.setData(h2.d.map((t, i) => ({ time: t, value: h2.up[i] ?? 0 })));
    dn.setData(h2.d.map((t, i) => ({ time: t, value: -(h2.dn[i] ?? 0) })));
    c.timeScale().fitContent();
  }
  const nm = $('#ns-more');
  if (nm) nm.onclick = () => { document.querySelectorAll('#ns-list li.more').forEach(li => li.style.display = ''); nm.remove(); };
  // 탭 강조
  const links = [...document.querySelectorAll('.tabs a')];
  links.forEach(a => a.addEventListener('click', e => {   // <base> 태그가 있는 정적 페이지에서도 페이지 안에서 이동
    e.preventDefault(); const s = document.getElementById(a.getAttribute('href').slice(1)); if (s) s.scrollIntoView({ behavior: 'smooth' }); }));
  document.querySelectorAll('.grid a.card[href^="#"]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault(); const s = document.getElementById(a.getAttribute('href').slice(1)); if (s) s.scrollIntoView({ behavior: 'smooth' }); }));
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id)); }), { rootMargin: '-120px 0px -60% 0px' });
  document.querySelectorAll('section[id]').forEach(s => io.observe(s));
  footer();
}

// ================================================================ ETF
async function renderEtf(U, d) {
  const m = d.m, K = await Data.krEtfs().catch(() => null);
  let h = headBlock(m, [m.grp, m.fam].filter(Boolean));
  h += card('', '', `<div class="kv">${[['순자산', fmtUsd(m.aum)], ['총보수', fmt(m.exp, 'pct2')], ['배당수익률(12개월)', fmt(m.dy, 'pct')], ['1개월', pctS(m.r1m)], ['연초 이후', pctS(m.rytd)], ['1년', pctS(m.r1y)],
    ['200일선 대비', pctS(m.d200)], ['52주 고가 대비', pctS(m.hi52)], ['변동성(60일)', fmt(m.vol, 'pct')], ['구성 종목 수', d.n_holdings || '-']].map(([a, b]) => `<div><span>${a}</span><b>${b}</b></div>`).join('')}</div>`);
  h += chartCard('pc');
  const H = d.holdings || [];
  const inU = new Set(U.rows.map(r => r.t));
  h += `<div class="grid g2">` + card(`구성 종목 <span class="faint small">${d.n_holdings || 0}개</span>`, d.hold_src ? `출처: ${esc(d.hold_src)} · 비중 상위 ${Math.min(60, H.length)}개` : '', H.length ? `<div class="tbl-wrap" style="max-height:520px;overflow-y:auto"><table class="t"><thead><tr><th>종목</th><th class="l">이름</th><th>비중</th></tr></thead><tbody>
    ${H.map(([t, n, w]) => `<tr><td>${t && inU.has(t) ? `<a href="${stockUrl(t)}">${esc(t)}</a>` : esc(t || '-')}</td><td class="l nm mut">${esc(n || '')}</td><td class="num">${w != null ? (+w).toFixed(2) + '%' : '-'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="mut s13">구성 자료가 없습니다 (원자재·선물·인버스형은 구성 공개 대상이 아니에요)</div>')
    + card('업종 비중', '', d.sectors ? Object.entries(d.sectors).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div style="display:grid;grid-template-columns:110px 1fr 48px;gap:8px;align-items:center;font-size:13px"><span>${secKo(k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace('Realestate', 'Real Estate'))}</span><div class="bar"><i style="width:${v * 100}%"></i></div><span class="num" style="text-align:right">${(v * 100).toFixed(1)}%</span></div>`).join('') : '<div class="mut s13">자료 없음</div>') + `</div>`;
  const kr = K ? K.rows.filter(k => k.us === m.t) : [];
  if (kr.length) h += card(`국내 상장 ${esc(m.t)} 대응 ETF <span class="faint small">${kr.length}개</span>`, '같은 지수를 따르는 국내 상장 ETF · 괴리율 = (시장가−NAV)/NAV · (H) = 환헤지', `<div class="tbl-wrap"><table class="t"><thead><tr><th>종목</th><th>순자산</th><th>20일 평균 거래대금</th><th>1개월</th><th>1년</th><th>괴리율</th></tr></thead><tbody>
    ${kr.sort((a, b) => (b.aum || 0) - (a.aum || 0)).map(k => `<tr><td class="nm">${esc(k.n)} <span class="faint small">${esc(k.code)}</span></td><td class="num">${fmtKrw(k.aum)}</td><td class="num">${fmtKrw(k.val)}</td><td>${pctS(k.r1m)}</td><td>${pctS(k.r1y)}</td><td class="num">${k.dev != null ? k.dev.toFixed(2) + '%' : '-'}</td></tr>`).join('')}</tbody></table></div>`);
  if (d.div && d.div.length) h += card('배당 이력', '최근 지급분 (주당, 달러)', `<div class="tbl-wrap"><table class="t"><thead><tr>${d.div.slice(-12).reverse().map(x => `<th>${fmt(x[0], 'date')}</th>`).join('')}</tr></thead><tbody><tr>${d.div.slice(-12).reverse().map(x => `<td class="num">$${(+x[1]).toFixed(4)}</td>`).join('')}</tr></tbody></table></div>`);
  if (d.summary) h += card('소개', '', `<p style="margin:0;font-size:14px;color:var(--muted)">${esc(d.summary)}</p>`);
  $('#app').innerHTML = h;
  document.title = `${m.t} ETF — ${m.n} 구성 종목·배당·수익률 | 티커맵`;
  mountChart('pc', d, true);
  footer();
}

// ================================================================ 시작 화면
async function renderHome(U) {
  const S = U.rows.filter(r => r.k === 'stock').sort((a, b) => (b.mcap || 0) - (a.mcap || 0));
  const E = U.rows.filter(r => r.k === 'etf').sort((a, b) => (b.aum || 0) - (a.aum || 0));
  const tile = r => `<a class="card" href="${stockUrl(r.t)}" style="color:inherit;text-decoration:none;gap:2px"><b>${r.t}</b><span class="small mut" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.n)}</span><span class="num">${fmt(r.px, 'px')} ${pctS(r.r1d)}</span></a>`;
  $('#app').innerHTML = `<div class="hero"><h1>종목</h1><p>위 검색창에 티커나 회사명을 입력하세요. 한 종목의 컨센서스·재무·차트·공시·뉴스를 한 화면에 모았어요.</p></div>
    <div class="sec-head"><h2>시가총액 상위</h2></div><div class="grid g4">${S.slice(0, 16).map(tile).join('')}</div>
    <div class="sec-head"><h2>순자산 상위 ETF</h2></div><div class="grid g4">${E.slice(0, 8).map(tile).join('')}</div>`;
  footer();
}

(async () => {
  try {
    const U = await Data.universe();
    if (!T) return renderHome(U);
    const row = U.rows.find(r => r.t === T);
    if (!row) { $('#app').innerHTML = `<div class="loading">${esc(T)} — 추적 대상이 아닌 종목입니다. 지금은 러셀 1000·나스닥 100 종목과 주요 ETF 159개를 다룹니다.</div>`; footer(); return; }
    if (row.k === 'etf') renderEtf(U, await Data.etf(T));
    else { const [d, P] = await Promise.all([Data.stock(T), Data.stockPro(T).catch(() => null)]); renderStock(U, d, P); }
  } catch (e) { $('#app').innerHTML = `<div class="loading">불러오지 못했습니다 (${esc(e.message)})</div>`; console.error(e); }
})();
