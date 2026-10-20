// investors.html 화면 (정적 페이지 /hub/s/·/hub/i/ 에서도 같이 씀)
header('유명 투자자');
const KIND = { guru: '유명 투자자', fund: '헤지펀드·퀀트', inst: '대형 운용사' };
let F, U, inU, sel = window.HUB_M ? +window.HUB_M : qs('m') ? +qs('m') : null, kindSel = qs('k') || 'guru';

const tk = (t, n) => t && inU.has(t) ? `<a href="${stockUrl(t)}"><b>${esc(t)}</b></a>` : `<b>${esc(t || '-')}</b>`;
const chgCell = x => x.new ? '<span class="up">신규</span>' : x.chg == null ? '-' : Math.abs(x.chg) < 0.005 ? '<span class="mut">유지</span>' : pctS(x.chg);
const wcell = w => w == null ? '-' : `<span class="wbar" style="width:${Math.min(40, w * 150)}px"></span>${(w * 100).toFixed(w < 0.01 ? 2 : 1)}%`;

function managerView(m) {
  const qtr = p => p ? `${p.slice(0, 4)}년 ${Math.ceil(+p.slice(5, 7) / 3)}분기` : '';
  let h = `<div class="card"><div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><h3 style="font-size:18px">${esc(m.m)}</h3><span class="tag">${KIND[m.k]}</span>
    <span class="mut s13">${qtr(m.p)} 말 기준 · ${esc(m.filed)} 제출${m.prev ? ` · ${qtr(m.prev)}과 비교` : ''}</span></div>
    <div class="kv"><div><span>보유 총액 (13F 신고분)</span><b>${fmtUsd(m.total)}</b></div><div><span>보유 종목 수</span><b>${m.n.toLocaleString()}${m.k !== 'guru' ? '+' : ''}</b></div>
      <div><span>상위 10종목 비중</span><b>${fmt(m.top10w, 'pct')}</b></div></div>
    ${m.k !== 'guru' ? '<div class="small faint">대형 기관은 평가액 상위 종목만 저장합니다 · 미국 상장 주식만 신고 대상(현금·채권·해외 주식·공매도 제외)</div>' : '<div class="small faint">13F는 미국 상장 주식 롱 포지션만 신고합니다 (현금·채권·해외 주식·공매도 제외)</div>'}</div>`;
  h += `<div class="grid g2"><div class="card"><h3>보유 상위 종목</h3><div class="tbl-wrap"><table class="t"><thead><tr><th>종목</th><th class="l">발행사</th><th>비중</th><th>평가액</th><th>주식 수 변화</th></tr></thead><tbody>
    ${m.top.map(x => `<tr><td>${tk(x.t)}</td><td class="l nm mut" style="max-width:150px">${esc((x.n || '').slice(0, 20))}</td><td class="num l">${wcell(x.w)}</td><td class="num">${fmtUsd(x.v)}</td><td>${chgCell(x)}</td></tr>`).join('')}</tbody></table></div></div>
    <div style="display:flex;flex-direction:column;gap:12px">
    <div class="card"><h3>이번 분기 산 종목</h3><div class="sub">늘린 주식 수 × 분기 말 가격 (가격 변동 제외)</div>${m.buys.length ? `<div class="tbl-wrap"><table class="t"><tbody>${m.buys.map(x => `<tr><td>${tk(x.t)}</td><td class="l nm mut">${esc((x.n || '').slice(0, 22))}</td><td class="num up">+${fmtUsd(x.dv)}</td><td>${x.new ? '<span class="up">신규</span>' : pctS(x.chg)}</td></tr>`).join('')}</tbody></table></div>` : `<div class="mut s13">${m.prev ? '산 종목이 없습니다' : '직전 분기 자료가 없어 비교할 수 없습니다'}</div>`}</div>
    <div class="card"><h3>이번 분기 판 종목</h3><div class="sub">줄인 주식 수 × 직전 분기 말 가격</div>${m.sells.length ? `<div class="tbl-wrap"><table class="t"><tbody>${m.sells.map(x => `<tr><td>${tk(x.t)}</td><td class="l nm mut">${esc((x.n || '').slice(0, 22))}</td><td class="num dn">${fmtUsd(x.dv)}</td><td>${x.out ? '<span class="dn">전량 매도</span>' : '<span class="mut">일부</span>'}</td></tr>`).join('')}</tbody></table></div>` : `<div class="mut s13">${m.prev ? '판 종목이 없습니다' : '직전 분기 자료가 없어 비교할 수 없습니다'}</div>`}</div>
    </div></div>`;
  return h;
}

function render() {
  const M = F.managers.filter(m => m.k === kindSel);
  let h = `<div class="hero"><h1>유명 투자자 포트폴리오</h1><p>운용자산 1억 달러 이상 기관이 분기마다 SEC에 내는 13F 보고서 기준 · 분기 종료 후 45일 안에 공개되므로 최대 4개월 반 늦은 정보예요</p></div>`;
  // 합산
  const pop = F.popular || [], bought = F.bought || [], sold = F.sold || [];
  const rl = (rows, val, sub) => rankList(rows.map(r => ({ ...r, t: r.ticker, cnt: r.n, n: r.name })), val, sub, 10);
  h += `<div class="grid g3">
    <div class="card"><h3>유명 투자자가 많이 가진 종목</h3><div class="sub">보유한 투자자 수 (평가액 합계 순)</div>${rl(pop, r => `${r.cnt}곳`, r => `${esc((r.name || '').slice(0, 20))} · ${fmtUsd(r.v)}`)}</div>
    <div class="card"><h3>이번 분기 많이 산 종목</h3><div class="sub">새로 사거나 5% 넘게 늘린 투자자 수</div>${rl(bought, r => `${r.b}곳`, r => `신규 ${r.new} · 늘림 ${r.up}`)}</div>
    <div class="card"><h3>이번 분기 다 판 종목</h3><div class="sub">전량 매도한 투자자 수</div>${rl(sold, r => `${r.s}곳`, r => esc((r.name || '').slice(0, 24)))}</div></div>`;
  h += `<div class="sec-head"><h2>투자자별</h2><span class="desc">눌러서 보유 종목과 이번 분기 매매를 확인하세요</span></div>
    <div class="seg">${Object.entries(KIND).map(([k, l]) => `<button class="btn ${k === kindSel ? 'on' : ''}" data-k="${k}">${l} <span class="faint small">${F.managers.filter(m => m.k === k).length}</span></button>`).join('')}</div>
    <div class="mgr-list">${M.map(m => `<button class="mgr ${m.cik === sel ? 'on' : ''}" data-m="${m.cik}"><b>${esc(m.m)}</b><span class="small">${fmtUsd(m.total)} · ${m.n.toLocaleString()}종목 · ${esc(m.p.slice(2, 7).replace('-', '.'))} 기준</span>
      <span class="small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${m.top.slice(0, 4).map(x => x.t || (x.n || '').split(' ')[0]).join(' · ')}</span></button>`).join('')}</div>
    <div id="mv"></div>`;
  $('#app').innerHTML = h;
  document.querySelectorAll('[data-k]').forEach(b => b.onclick = () => { kindSel = b.dataset.k; sel = null; sync(); render(); });
  document.querySelectorAll('[data-m]').forEach(b => b.onclick = () => { sel = +b.dataset.m; sync(); render(); $('#mv').scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  const m = F.managers.find(x => x.cik === sel) || (sel == null ? null : null);
  $('#mv').innerHTML = m ? managerView(m) : '';
  footer();
}
function sync() { const u = new URL(location.href); u.searchParams.set('k', kindSel); sel ? u.searchParams.set('m', sel) : u.searchParams.delete('m'); history.replaceState(null, '', u); }

(async () => {
  try { [F, U] = await Promise.all([Data.f13(), Data.universe()]); }
  catch (e) { $('#app').innerHTML = `<div class="loading">불러오지 못했습니다 (${esc(e.message)})</div>`; return; }
  inU = new Set(U.rows.map(r => r.t));
  if (sel) { const m = F.managers.find(x => x.cik === sel); if (m) kindSel = m.k; }
  else sel = (F.managers.find(m => m.k === kindSel) || {}).cik ?? null;
  render();
})();
