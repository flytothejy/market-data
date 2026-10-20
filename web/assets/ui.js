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
function header(active) {
  const items = [['index.html', '둘러보기'], ['stock.html', '종목'], ['screen.html', '검색'], ['compare.html', '비교'], ['earnings.html', '실적 달력'], ['investors.html', '유명 투자자'], ['portfolio.html', '포트폴리오']];
  const el = document.createElement('header');
  el.className = 'top';
  el.innerHTML = `<div class="in"><a class="brand" href="index.html">종목 허브</a>
  <nav class="main">${items.map(([h, l]) => `<a href="${h}" class="${l === active ? 'on' : ''}">${l}</a>`).join('')}</nav>
  <div class="search"><input type="search" placeholder="티커·회사명 (한글 가능)" aria-label="종목 검색" autocomplete="off"><div class="sugg"></div></div></div>`;
  document.body.prepend(el);
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
  f.innerHTML = '출처: SEC EDGAR(공시·재무·내부자·13F) · FINRA(공매도 거래) · yfinance(가격·컨센서스·개요·옵션) · 공공데이터포털(국내 ETF) · 각 운용사(ETF 구성)<br>정보 제공용이며 투자 권유가 아닙니다';
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

// ---- 관심 종목 (이 브라우저에 저장 — 로그인이 붙으면 서버 저장으로 바꿈)
const Watch = {
  KEY: 'hub.watch.v1',
  list() { try { return JSON.parse(localStorage.getItem(this.KEY)) || []; } catch (e) { return this._mem || []; } },
  save(a) { this._mem = a; try { localStorage.setItem(this.KEY, JSON.stringify(a)); } catch (e) { } },
  has(t) { return this.list().includes(t); },
  toggle(t) { const a = this.list(); const i = a.indexOf(t); i >= 0 ? a.splice(i, 1) : a.unshift(t); this.save(a); return i < 0; },
};
// 포트폴리오 보유 종목 (포트폴리오 화면과 같은 저장소)
function portfolioTickers() {
  try { const p = JSON.parse(localStorage.getItem('hub.portfolio.v1')); return (p && p.items || []).map(x => x.t); } catch (e) { return []; }
}
const watchBtn = t => `<button class="btn watch ${Watch.has(t) ? 'on' : ''}" data-watch="${esc(t)}" aria-pressed="${Watch.has(t)}">${Watch.has(t) ? '★ 관심 종목' : '☆ 관심 종목에 추가'}</button>`;
document.addEventListener('click', e => {
  const b = e.target.closest('[data-watch]');
  if (!b) return;
  e.preventDefault();
  const on = Watch.toggle(b.dataset.watch);
  document.querySelectorAll(`[data-watch="${CSS.escape(b.dataset.watch)}"]`).forEach(x => {
    x.classList.toggle('on', on); x.setAttribute('aria-pressed', on);
    if (x.classList.contains('watch')) x.textContent = on ? '★ 관심 종목' : '☆ 관심 종목에 추가';
    else x.textContent = on ? '★' : '☆';
  });
  document.dispatchEvent(new CustomEvent('watch-change'));
});
const starBtn = t => `<button class="star ${Watch.has(t) ? 'on' : ''}" data-watch="${esc(t)}" title="관심 종목" aria-label="${esc(t)} 관심 종목">${Watch.has(t) ? '★' : '☆'}</button>`;

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
