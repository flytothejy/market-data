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
  const items = [['index.html', '둘러보기'], ['stock.html', '종목'], ['screen.html', '검색'], ['portfolio.html', '포트폴리오']];
  const el = document.createElement('header');
  el.className = 'top';
  el.innerHTML = `<div class="in"><a class="brand" href="index.html">종목 허브</a>
  <nav class="main">${items.map(([h, l]) => `<a href="${h}" class="${l === active ? 'on' : ''}">${l}</a>`).join('')}</nav>
  <div class="search"><input type="search" placeholder="티커 또는 회사명" aria-label="종목 검색" autocomplete="off"><div class="sugg"></div></div></div>`;
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
  const go = r => location.href = `stock.html?t=${encodeURIComponent(r.t)}`;
  inp.addEventListener('input', async () => {
    const q = inp.value.trim().toUpperCase();
    if (!q) { box.style.display = 'none'; return; }
    const u = await Data.universe();
    const ql = q.toLowerCase();
    const a = u.rows.filter(r => r.t === q), b = u.rows.filter(r => r.t !== q && r.t.startsWith(q)),
      c = u.rows.filter(r => !r.t.startsWith(q) && (r.n || '').toLowerCase().includes(ql));
    list = [...a, ...b.sort((x, y) => (y.mcap || y.aum || 0) - (x.mcap || x.aum || 0)), ...c.sort((x, y) => (y.mcap || y.aum || 0) - (x.mcap || x.aum || 0))].slice(0, 8);
    sel = -1;
    box.innerHTML = list.map((r, i) => `<a href="stock.html?t=${encodeURIComponent(r.t)}" data-i="${i}"><b>${esc(r.t)}</b><span>${esc(r.n)}${r.k === 'etf' ? ' · ETF' : ''}</span></a>`).join('') || '<a><span>결과 없음</span></a>';
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
  return `<div class="rank">${rows.slice(0, n).map((r, i) => `<a class="r" href="stock.html?t=${encodeURIComponent(r.t)}">
    <span class="i num">${i + 1}</span><span class="nm"><b>${esc(r.t)}</b><small>${esc(sub ? sub(r) : r.n)}</small></span><span class="v num">${val(r)}</span></a>`).join('')}</div>`;
}

function lockBox(inner, msg = '프로 멤버십에서 볼 수 있어요') {
  return `<div class="locked"><div class="blur">${inner}</div><div class="over"><span class="pro">PRO</span><b>${esc(msg)}</b></div></div>`;
}

const qs = k => new URLSearchParams(location.search).get(k);
