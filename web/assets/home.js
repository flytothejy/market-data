// 홈 — 맨 위: 오늘의 소식(설정으로 끄기), 티커맵(버블·히트맵 — 설정), 아래: 시장 요약·관심 종목·티커랭킹 미리보기
header('');
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const idxName = { SPY: 'S&P 500', QQQ: '나스닥 100', DIA: '다우 30', IWM: '러셀 2000' };
const sgn = (v, d = 0) => (v > 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
const card = (title, sub, body) => `<div class="card"><h3>${title}</h3>${sub ? `<div class="sub">${sub}</div>` : ''}${body}</div>`;

// 작은 티커맵: EPS 전망 렌즈 × 1개월 주가, 시가총액 100억 달러 이상 (티커맵의 기본 화면과 같은 기준)
const XM = 0.3, YM = 0.3;
function mapPoints(S) {
  return S.filter(r => r.r1m != null && r.c_chg90 != null && (r.c_n || 0) >= 3 && (r.mcap || 0) >= 1e10).map(r => {
    const xN = Math.max(-1, Math.min(1, r.r1m / XM)), yN = Math.max(-1, Math.min(1, r.c_chg90 / YM));
    const quad = yN > 0.03 && r.r1m < -0.003 ? 'tl' : yN < -0.03 && r.r1m > 0.003 ? 'br' : 'n';
    return { r, xN, yN, quad, score: Math.min(Math.abs(xN), Math.abs(yN)) + 0.3 * (Math.abs(xN) + Math.abs(yN)) };
  });
}
const pick = (P, q, n) => P.filter(p => p.quad === q && Math.abs(p.yN) > 0.06 && Math.abs(p.xN) > 0.06).sort((a, b) => b.score - a.score).slice(0, n);

function miniMap(P, W, H) {
  const pl = 18, pr = 18, pt = 36, pb = 30, iw = W - pl - pr, ih = H - pt - pb;
  const sx = v => pl + (v + 1.04) / 2.08 * iw, sy = v => pt + (1 - (v + 1.04) / 2.08) * ih;
  const up = cssv('--up'), dn = cssv('--dn');
  const hot = new Set([...pick(P, 'tl', 6), ...pick(P, 'br', 6)].map(p => p.r.t));
  let g = `<rect x="${sx(-1.04)}" y="${sy(1.04)}" width="${sx(0) - sx(-1.04)}" height="${sy(0) - sy(1.04)}" fill="color-mix(in srgb, var(--up) 9%, var(--card))"/>
    <rect x="${sx(0)}" y="${sy(0)}" width="${sx(1.04) - sx(0)}" height="${sy(-1.04) - sy(0)}" fill="color-mix(in srgb, var(--dn) 9%, var(--card))"/>
    <line x1="${sx(0)}" x2="${sx(0)}" y1="${pt}" y2="${pt + ih}" stroke="var(--line)" stroke-width="1.2"/><line x1="${pl}" x2="${pl + iw}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line)" stroke-width="1.2"/>
    <text x="${sx(-1.04) + 10}" y="${sy(0) - 10}" font-size="${W < 600 ? 12 : 13.5}" font-weight="800" fill="${up}">전망은 오르는데 주가는 빠짐</text>
    <text x="${sx(1.04) - 10}" y="${sy(0) + 20}" font-size="${W < 600 ? 12 : 13.5}" font-weight="800" text-anchor="end" fill="${dn}">주가는 오르는데 전망은 꺾임</text>
    <text x="${pl}" y="${pt - 12}" font-size="11.5" fill="var(--muted)">↑ 내년 EPS 전망 (90일 변화)</text>
    <text x="${pl + iw}" y="${H - 8}" font-size="11.5" text-anchor="end" fill="var(--muted)">최근 1개월 주가 →</text>`;
  const maxM = Math.max(...P.map(p => p.r.mcap || 0), 1);
  const sorted = P.slice().sort((a, b) => (b.r.mcap || 0) - (a.r.mcap || 0));
  for (const p of sorted) {
    const rad = 2.6 + Math.sqrt((p.r.mcap || 0) / maxM) * (W < 600 ? 16 : 24), cx = sx(p.xN), cy = sy(p.yN);
    const col = p.quad === 'tl' ? up : p.quad === 'br' ? dn : 'var(--faint)', op = p.quad === 'n' ? 0.3 : 0.72;
    g += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad.toFixed(1)}" fill="${col}" fill-opacity="${op}" stroke="${col}" stroke-opacity=".85"/>`;
    p._x = cx + rad + 3; p._y = cy + 4;
  }
  for (const p of sorted.filter(p => hot.has(p.r.t)))
    g += `<text x="${p._x.toFixed(1)}" y="${p._y.toFixed(1)}" font-size="12" font-weight="800" fill="var(--ink)" paint-order="stroke" stroke="var(--card)" stroke-width="3" stroke-linejoin="round">${esc(p.r.t)}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="오늘의 티커맵 미리보기: 가로 최근 1개월 주가, 세로 내년 EPS 전망 변화">${g}</svg>`;
}

// ---- 오늘의 소식: 그날 볼거리를 골라 보여 줌 (후보함 알림의 '모두에게' 버전) — 전부 화면용 데이터에서 계산
const WDK = '일월화수목금토';
const dayK = d => `${+d.slice(5, 7)}/${+d.slice(8, 10)}(${WDK[new Date(d + 'T12:00:00Z').getUTCDay()]})`;
const addD = (d, n) => { const x = new Date(d + 'T12:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const nextTD = d => { let x = addD(d, 1); while ([0, 6].includes(new Date(x + 'T12:00:00Z').getUTCDay())) x = addD(x, 1); return x; };   // 다음 거래일 (휴장일은 무시)
const prevTD = d => { let x = addD(d, -1); while ([0, 6].includes(new Date(x + 'T12:00:00Z').getUTCDay())) x = addD(x, -1); return x; };
function briefCards(U, F) {
  const S = U.rows.filter(r => r.k === 'stock'), asof = U.asof, byCap = a => a.sort((x, y) => (y.mcap || 0) - (x.mcap || 0));
  const name = r => shortName(r);
  const row = (r, d) => `<div class="bf-r"><a href="${stockUrl(r.t)}"><b>${esc(r.t)}</b><span class="cn">${esc(name(r))}</span><span class="d">${d}</span></a>${starBtn(r.t)}</div>`;
  const cards = [], N = innerWidth < 700 ? 4 : 6;   // 휴대폰은 카드마다 4줄
  const add = (key, color, title, sub, rows, more) => rows.length && cards.push({ key, html: `<div class="card"><h3><span class="dot" style="background:${color}"></span>${title}</h3>${sub ? `<div class="sub">${sub}</div>` : ''}<div>${rows.join('')}</div>${more ? `<div class="bf-more">${more}</div>` : ''}</div>` });
  // 1) 실적 결과 — 직전 2거래일 안에 발표
  const p1 = prevTD(asof);
  const er = byCap(S.filter(r => r.er_d && r.er_d >= p1 && r.er_d <= asof && r.er_eps_s != null));
  const good = er.filter(r => r.er_eps_s > 0.02).length, bad = er.filter(r => r.er_eps_s < -0.02).length;
  add('er', 'var(--accent)', `실적 발표 ${er.length}곳`, `${dayK(p1)}~${dayK(asof)} · EPS가 예상보다 좋음 ${good} · 못 미침 ${bad}`,
    er.slice(0, N).map(r => row(r, `EPS ${pctS(r.er_eps_s)}${r.er_mv != null ? ` <span class="mut">· 다음 날 ${fmt(r.er_mv, 'pct', { sign: true })}</span>` : ''}`)),
    er.length > N ? `<a href="earnings.html">실적 달력에서 ${er.length - N}곳 더 →</a>` : '');
  // 2) 다음 거래일 실적 발표
  const nx = nextTD(asof), up = byCap(S.filter(r => r.c_next === nx));
  add('next', '#7c3aed', `${dayK(nx)} 실적 발표 예정 ${up.length}곳`, '미국 시간 · 장 전 = 개장 전, 장 후 = 마감 뒤',
    up.slice(0, N).map(r => row(r, `<span class="mut">${esc(r.c_when || '')}</span>${r.er_avg ? ` <span class="mut">· 평소 ±${fmt(r.er_avg, 'pct')}</span>` : ''}`)),
    up.length > N ? `<a href="earnings.html">실적 달력에서 ${up.length - N}곳 더 →</a>` : '');
  // 3) 평소보다 크게 움직인 종목 — 하루 변동을 평소 하루 변동폭(연 변동성/√252)으로 나눈 배수
  const mv = S.filter(r => (r.mcap || 0) >= 5e9 && r.r1d != null && r.vol > 0).map(r => ({ r, z: r.r1d / (r.vol / Math.sqrt(252)) })).filter(x => Math.abs(x.z) >= 3).sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
  add('move', 'var(--up)', `평소보다 크게 움직인 종목 ${mv.length}개`, `${dayK(asof)} · 평소 하루 변동폭의 3배 넘게 · 시가총액 50억 달러 이상`,
    mv.slice(0, N).map(x => row(x.r, `${pctS(x.r.r1d)} <span class="mut">· ${Math.abs(x.z).toFixed(1)}배</span>`)));
  // 4) 임원 장내 매수 — 최근 5일 안에 신고된 것
  const ins = S.filter(r => r.ib >= 3e5 && r.ib_last && r.ib_last >= addD(asof, -5)).sort((a, b) => b.ib - a.ib);
  add('ins', 'var(--good)', `임원 장내 매수 ${ins.length}곳`, '최근 5일 안에 신고 · 90일 합계 금액',
    ins.slice(0, N).map(r => row(r, `${fmtUsd(r.ib)} <span class="mut">· ${r.ibn || 1}명</span>`)));
  // 5) 52주 신고가 — 대형주
  const hi = byCap(S.filter(r => (r.mcap || 0) >= 1e10 && r.hi52 != null && r.hi52 >= -0.001 && r.r1d > 0));
  add('hi', '#b45309', `52주 신고가 ${hi.length}곳`, `${dayK(asof)} · 시가총액 100억 달러 이상`, hi.slice(0, N).map(r => row(r, `${pctS(r.r1d)} <span class="mut">· 1년 ${fmt(r.r1y, 'pct', { sign: true })}</span>`)));
  // 6) 유명 투자자 새 13F — 최근 10일 안에 공개
  const mg = ((F && F.managers) || []).filter(m => m.filed && m.filed >= addD(asof, -10)).sort((a, b) => (b.total || 0) - (a.total || 0));
  if (mg.length) cards.push({ key: 'f13', html: `<div class="card"><h3><span class="dot" style="background:#0f766e"></span>유명 투자자 13F 공개 ${mg.length}곳</h3><div class="sub">최근 10일 · 분기 말 기준 보유 종목</div><div>${mg.slice(0, 5).map(m => {
      const buys = (m.buys || []).filter(x => x.t).slice(0, 3).map(x => x.t).join(', ');
      return `<div class="bf-r"><a href="i/${m.cik}/"><b>${esc(m.m)}</b><span class="d mut">${buys ? '산 종목 ' + esc(buys) : ''}</span></a><span></span></div>`; }).join('')}</div></div>` });
  return cards;
}

(async () => {
  let U, M;
  try { [U, M] = await Promise.all([Data.universe(), Data.market()]); }
  catch (e) { $('#app').innerHTML = `<div class="loading">데이터를 불러오지 못했습니다 (${esc(e.message)})</div>`; return; }
  const S = U.rows.filter(r => r.k === 'stock');
  const P = mapPoints(S);
  const tl = pick(P, 'tl', 5), br = pick(P, 'br', 5);
  const row = p => `<a href="matrix.html?t=${encodeURIComponent(p.r.t)}"><b>${esc(p.r.t)}</b><small>${esc(p.r.ko || p.r.n || '')}</small><span class="v">주가 ${sgn(p.r.r1m)} · 전망 ${sgn(p.r.c_chg90)}</span></a>`;
  // 시장 요약 (오늘의 소식을 켜면 그 맨 위, 끄면 지도 아래)
  const mkt = head => `${head ? `<div class="sec-head"><h2>오늘의 시장</h2><span class="desc">${esc(M.asof)} 종가</span></div>` : ''}
    <div class="grid g4">${Object.entries(M.indices).map(([t, x]) => `<a class="card" href="${stockUrl(t)}" style="color:inherit;text-decoration:none;gap:2px">
      <div class="mut s13">${idxName[t] || t} <span class="faint">${t}</span></div>
      <div style="display:flex;align-items:baseline;gap:8px"><b style="font-size:20px" class="num">${fmt(x.px, 'px')}</b>${pctS(x.r1d)}</div>
      <div class="small mut">1개월 ${pctS(x.r1m)} · 연초 이후 ${pctS(x.rytd)}</div></a>`).join('')}</div>
    <div class="card"><div class="kv">
      <div><span>상승 / 하락 종목</span><b><span class="up">${M.adv}</span> / <span class="dn">${M.dec}</span></b></div>
      <div><span>200일선 위 종목 비율</span><b>${fmt(M.breadth_200, 'pct')}</b></div>
      <div><span>52주 신고가 / 신저가</span><b>${M.new_hi} / ${M.new_lo}</b></div>
      ${M.vix != null ? `<div><span>VIX (변동성 지수)</span><b>${M.vix.toFixed(1)}</b></div>` : ''}</div></div>`;
  const showBrief = Prefs.get('home.brief');
  let h = '';
  if (showBrief) {
    h += `<div class="hero"><h1>오늘의 소식</h1><p>미국 ${dayK(U.asof)} 마감 기준 · 매일 아침 새로 골라요 · 종목을 누르면 자세히, ☆로 후보함에</p></div>${mkt(false)}<div class="bf" id="brief">${briefCards(U, null).map(c => c.html).join('')}</div>`;
    h += `<div class="sec-head map-head"><h2>티커맵</h2><span class="desc" id="map-desc"></span><div class="mx-seg" role="tablist" aria-label="지도 모양"><button data-mode="bubble">● 버블</button><button data-mode="heat">▦ 히트맵</button></div></div>`;
  } else {
    h += `<div class="hero map-head"><div><h1>주가와 신호가 어긋난 종목, 티커맵에서</h1><p id="map-desc"></p></div><div class="mx-seg" role="tablist" aria-label="지도 모양"><button data-mode="bubble">● 버블</button><button data-mode="heat">▦ 히트맵</button></div></div>`;
  }
  h += `<div class="home-map" id="home-map"><a class="mini" href="matrix.html" id="mini" aria-label="티커맵 열기"></a>
    <div style="display:flex;flex-direction:column;gap:12px">
      <div class="card"><h3 style="color:var(--up)">전망은 오르는데 주가는 빠짐</h3><div class="hl">${tl.map(row).join('') || '<span class="mut s13">오늘은 없어요</span>'}</div></div>
      <div class="card"><h3 style="color:var(--dn)">주가는 오르는데 전망은 꺾임</h3><div class="hl">${br.map(row).join('') || '<span class="mut s13">오늘은 없어요</span>'}</div></div>
      <div class="small faint">시가총액 100억 달러 이상 · 종목을 누르면 티커맵에서 지나온 길(티커 트레일)을 보여줘요</div>
    </div></div><div class="home-map heat" id="home-heat" style="display:none"><div class="mini hm-mini" id="mini-heat"></div></div>`;
  if (!showBrief) h += mkt(true);
  // 내 관심 종목
  const Wl = Watch.list().map(t => U.rows.find(r => r.t === t)).filter(Boolean);
  if (Wl.length) {
    h += `<div class="sec-head"><h2>내 후보함</h2><span class="desc">${Wl.length}개 · <a href="watch.html">후보함 →</a></span>
      <a class="more" href="matrix.html?t=${encodeURIComponent(Wl.filter(r => r.k === 'stock').slice(0, 5).map(r => r.t).join(','))}">티커맵에서 보기 →</a></div>
      <div class="card"><div class="tbl-wrap"><table class="t"><thead><tr><th>종목</th><th>종가</th><th>1일</th><th>1개월</th><th>다음 실적</th><th class="l">한 줄 요약</th><th></th></tr></thead><tbody>
      ${Wl.map(r => `<tr><td><a href="${stockUrl(r.t)}"><b>${esc(r.t)}</b></a> <span class="mut small">${esc((r.ko || r.n || '').slice(0, 16))}</span></td><td class="num">${fmt(r.px, 'px')}</td><td>${pctS(r.r1d)}</td><td>${pctS(r.r1m)}</td>
        <td class="num">${r.c_next ? esc(r.c_next.slice(5)) : '-'}</td><td class="l nm mut" style="max-width:360px">${esc(r.s1 || '')}</td><td>${starBtn(r.t)}</td></tr>`).join('')}
      </tbody></table></div></div>`;
  }
  // 티커랭킹 미리보기
  const by = (arr, k) => arr.filter(r => r[k] != null).sort((a, b) => b[k] - a[k]);
  const big = S.filter(r => (r.mcap || 0) >= 1e10), consN = S.filter(r => (r.c_n || 0) >= 5);
  const sub = r => `${secKo(r.sec)} · ${fmtUsd(r.mcap)}`;
  const today = new Date().toISOString().slice(0, 10), wk = new Date(Date.now() + 8 * 864e5).toISOString().slice(0, 10);
  const earn = S.filter(r => r.c_next && r.c_next >= today && r.c_next <= wk).sort((a, b) => a.c_next < b.c_next ? -1 : a.c_next > b.c_next ? 1 : (b.mcap || 0) - (a.mcap || 0));
  h += `<div class="sec-head"><h2>티커랭킹</h2><span class="desc">오늘의 순위 일부</span><a class="more" href="ranking.html">전체 보기 →</a></div>
    <div class="grid g3">
    ${card('전망 상향이 많은 종목', '최근 30일 내년 EPS 상향−하향 / 애널리스트 수', rankList(consN.filter(r => r.c_ratio != null).sort((a, b) => b.c_ratio - a.c_ratio || (b.c_up || 0) - (a.c_up || 0)), r => pctS(r.c_ratio), r => `상향 ${r.c_up ?? 0} · 하향 ${r.c_dn ?? 0}`, 6))}
    ${card('다가오는 실적 발표 <a class="small" href="earnings.html" style="font-weight:400">달력 →</a>', '앞으로 일주일', rankList(earn, r => `<span class="mut">${esc(r.c_next.slice(5))}</span>`, sub, 6))}
    ${card('내부자 매수', '최근 90일 장내 매수 금액 (Form 4)', rankList(by(S.filter(r => r.ib > 0), 'ib'), r => fmtUsd(r.ib), r => `${r.ibn}명 · 최근 ${fmt(r.ib_last, 'date')}`, 6))}
    ${card('목표가 상승여력', '평균 목표가 / 현재가 − 1', rankList(by(consN, 'c_upside'), r => pctS(r.c_upside), sub, 6))}
    ${card('매출 성장이 빠른 종목', '최근 4개 분기, 1년 전 대비 · 시가총액 100억 달러 이상', rankList(by(big.filter(r => (r.rev || 0) >= 1e9), 'rev_g'), r => pctS(r.rev_g), r => `매출 ${fmtUsd(r.rev)}`, 6))}
    ${card('52주 신고가 부근', '고가 대비 −2% 이내, 3개월 수익률 순', rankList(by(S.filter(r => r.hi52 != null && r.hi52 >= -0.02), 'r3m'), r => pctS(r.r3m), r => `${secKo(r.sec)} · 1일 ${fmt(r.r1d, 'pct', { sign: true })}`, 6))}
    </div>`;
  $('#app').innerHTML = h;
  // 지도 모양: 설정의 '티커맵 처음 보기'를 따름 (여기서 바꾸면 설정에도 저장)
  const DESC = { bubble: `애널리스트 전망과 주가가 반대로 간 종목 · ${esc(M.asof)} 종가 기준`, heat: `업종별 오늘 시장 · 크기 = 시가총액 · ${esc(M.asof)} 종가 기준` };
  const draw = () => {
    const mode = Prefs.get('map.mode') === 'heat' ? 'heat' : 'bubble';
    document.querySelectorAll('.map-head .mx-seg button').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
    $('#map-desc').innerHTML = DESC[mode];
    $('#home-map').style.display = mode === 'bubble' ? '' : 'none';
    $('#home-heat').style.display = mode === 'heat' ? '' : 'none';
    if (mode === 'bubble') { const el = $('#mini'); const W = Math.max(300, el.clientWidth); el.innerHTML = miniMap(P, W, W < 600 ? Math.round(W * 0.95) : Math.min(520, Math.round(W * 0.62))) + '<span class="open">티커맵 열기 →</span>'; }
    else { const el = $('#mini-heat'); const W = Math.max(300, el.clientWidth); Heat.mini(el, U, W < 600 ? Math.round(W * 1.25) : Math.min(560, Math.round(W * 0.5))); el.insertAdjacentHTML('beforeend', '<a class="open" href="matrix.html?mode=heat" style="text-decoration:none">히트맵 크게 보기 →</a>'); }
  };
  draw();
  document.querySelectorAll('.map-head .mx-seg button').forEach(b => b.onclick = () => Prefs.set('map.mode', b.dataset.mode));
  document.addEventListener('prefs-change', draw);
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(draw, 150); });
  if (showBrief) Data.f13().then(F => { const el = $('#brief'); if (el) el.innerHTML = briefCards(U, F).map(c => c.html).join(''); }).catch(() => { });
  footer();
})();
