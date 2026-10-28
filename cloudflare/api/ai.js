// AI 문장 검색 — 문장 → 조건 JSON 번역 (features/ai-screen/README.md)
// AI는 조건만 만들고 종목은 모름. 결과는 여기서 다시 검사한 뒤 화면으로
//
// 설정: Secret ANTHROPIC_API_KEY (없으면 404 → 화면은 '곧 열려요')
//       Variable AI_MODEL (기본 claude-haiku-5-5), AI_LIMIT_USER(기본 30)·AI_LIMIT_ANON(기본 10) 하루 횟수
//       Variable DATA_URL (기본 https://tickermap.kr/api/v1) — 필드 사전 screen_catalog.json을 읽는 곳
import PROMPT from './ai_prompt.txt';

const DAY = 864e5;
const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);     // 한국 날짜 기준으로 하루 횟수
async function sha(s) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}

// ---- 필드 사전 (사이트 데이터, 1시간 캐시)
let _cat = null, _catAt = 0;
async function catalog(env, ctx) {
  if (_cat && Date.now() - _catAt < 3600e3) return _cat;
  const url = (env.DATA_URL || 'https://tickermap.kr/api/v1').replace(/\/$/, '') + '/free/screen_catalog.json';
  const cache = caches.default, key = new Request(url);
  let r = await cache.match(key);
  if (!r) {
    r = await fetch(url, { cf: { cacheTtl: 3600 } });
    if (!r.ok) throw new Error('catalog ' + r.status);
    const copy = new Response(r.clone().body, r);
    copy.headers.set('cache-control', 'max-age=3600');
    ctx.waitUntil(cache.put(key, copy));
  }
  const c = await r.json();
  c.map = Object.fromEntries(c.fields.map(f => [f.k, f]));
  c.text = promptFields(c);
  _cat = c; _catAt = Date.now();
  return c;
}
const short = x => typeof x === 'number' ? +x.toPrecision(3) : x;
function promptFields(c) {
  const L = ['FIELDS (key | 이름 | type | unit | 뜻 | 사람들이 쓰는 말 | 주의 | 분포 p10/p50/p90 | 값 있는 비율)'];
  for (const f of c.fields) {
    const dist = f.p50 != null ? `${short(f.p10)}/${short(f.p50)}/${short(f.p90)}` : '';
    const vals = f.values ? ' values=' + JSON.stringify(f.values) : '';
    L.push([f.k, f.label, f.type, f.unit, f.desc, f.say || '', f.note || '', dist, f.coverage != null ? Math.round(f.coverage * 100) + '%' : ''].join(' | ') + vals);
  }
  L.push('', 'VAGUE (모호한 말 기본값): ' + JSON.stringify(c.vague));
  L.push('추천·예측으로 보는 말: ' + (c.refuse || []).join(', '));
  return L.join('\n');
}

// ---- AI 출력 검사: 사전에 없는 key·틀린 형태는 버리고 unsupported로
export function validate(raw, cat) {
  const out = { kind: raw && raw.kind === 'etf' ? 'etf' : 'stock', conds: [], sort: null, assumptions: [], unsupported: [], refused: null };
  const strs = a => (Array.isArray(a) ? a : []).filter(x => typeof x === 'string' && x.trim()).map(x => x.trim().slice(0, 200)).slice(0, 6);
  out.assumptions = strs(raw && raw.assumptions);
  out.unsupported = strs(raw && raw.unsupported);
  if (raw && typeof raw.refused === 'string' && raw.refused.trim()) { out.refused = raw.refused.trim().slice(0, 400); return out; }
  const num = v => typeof v === 'number' && isFinite(v) ? v : (typeof v === 'string' && v.trim() !== '' && isFinite(+v) ? +v : null);
  const seen = new Set();
  for (const c of (Array.isArray(raw && raw.conds) ? raw.conds : []).slice(0, 12)) {
    const f = c && cat.map[c.k];
    if (!f) { if (c && c.k) out.unsupported.push(String(c.k).slice(0, 40)); continue; }
    if (seen.has(c.k)) continue;
    let ok = null;
    if (f.type === 'range') {
      let a = num(c.min), b = num(c.max);
      if (f.unit.startsWith('ratio')) {                         // 4를 4%로 쓴 경우: 분포 상위 10%의 10배(최소 1)를 넘으면 %로 봄
        const lim = Math.max(1, 10 * Math.abs(f.p90 || 0.1)), big = v => v != null && Math.abs(v) > lim;
        const fix = v => (big(v) ? v / 100 : v);
        if (big(a) || big(b)) out.assumptions.push(`${f.label} 값을 %로 보고 고쳤어요`);
        a = fix(a); b = fix(b);
      }
      if (a != null && b != null && a > b) [a, b] = [b, a];
      if (a != null || b != null) ok = { k: c.k, ...(a != null ? { min: a } : {}), ...(b != null ? { max: b } : {}) };
    } else if (f.type === 'date') {
      const p = num(c.past_days), n = num(c.next_days);
      if (p != null && p >= 1 && p <= 3650) ok = { k: c.k, past_days: Math.round(p) };
      else if (n != null && n >= 1 && n <= 365) ok = { k: c.k, next_days: Math.round(n) };
    } else if (f.type === 'enum') {
      let vs = Array.isArray(c.in) ? c.in : c.in != null ? [c.in] : [];
      if (f.values) vs = vs.filter(v => Object.prototype.hasOwnProperty.call(f.values, v));
      vs = vs.filter(v => ['string', 'number'].includes(typeof v)).slice(0, 12);
      if (vs.length) ok = { k: c.k, in: vs };
    } else if (f.type === 'flag') {
      const v = num(c.is);
      if (v === 0 || v === 1) ok = { k: c.k, is: v };
    }
    if (ok) { out.conds.push(ok); seen.add(c.k); } else out.unsupported.push(f.label);
  }
  const s = raw && raw.sort;
  if (s && cat.map[s.k] && cat.map[s.k].type === 'range') out.sort = { k: s.k, dir: s.dir === 'asc' ? 'asc' : 'desc' };
  out.unsupported = [...new Set(out.unsupported)].slice(0, 6);
  return out;
}

function parseJSON(t) {
  t = String(t || '').replace(/```(json)?/g, '');
  const a = t.indexOf('{'), b = t.lastIndexOf('}');
  if (a < 0 || b <= a) return null;
  try { return JSON.parse(t.slice(a, b + 1)); } catch (e) { return null; }
}

async function claude(env, cat, q) {
  const body = {
    model: env.AI_MODEL || 'claude-haiku-5-5', max_tokens: 900,
    system: [
      { type: 'text', text: PROMPT },
      { type: 'text', text: cat.text, cache_control: { type: 'ephemeral' } },
      { type: 'text', text: `오늘 날짜: ${today()} (데이터 기준일 ${cat.version || '-'})` },
    ],
    messages: [{ role: 'user', content: q }],
  };
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error('claude ' + r.status + ' ' + ((j.error && j.error.message) || '').slice(0, 120));
  return { text: (j.content || []).filter(c => c.type === 'text').map(c => c.text).join(''), usage: j.usage || {} };
}

// who: 로그인 계정이면 'u:<id>', 아니면 IP를 하루 단위로 해시 (원래 IP는 저장 안 함)
export async function aiScreen(req, env, ctx, who, h) {
  const send = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', ...h } });
  if (!env.ANTHROPIC_API_KEY) return send({ error: 'soon' }, 404);
  const b = await req.json().catch(() => ({}));
  const q = String(b.q || '').replace(/\s+/g, ' ').trim();
  if (q.length < 2) return send({ error: 'empty' }, 400);
  if (q.length > 300) return send({ error: 'too long' }, 400);
  const day = today(), t0 = Date.now();
  const cat = await catalog(env, ctx);
  const qh = await sha(q.toLowerCase() + '|' + (cat.version || '') + '|' + PROMPT.length + '|' + (env.AI_MODEL || ''));   // 사전·프롬프트·모델이 바뀌면 새로
  const log = (res, extra) => ctx.waitUntil(env.DB.prepare('INSERT INTO ai_log (ts, day, who, q, res, n, unsup, refused, ms, cached, tok_in, tok_out) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)')
    .bind(t0, day, who, q, JSON.stringify(res), res.conds ? res.conds.length : 0, JSON.stringify(res.unsupported || []), res.refused ? 1 : 0, Date.now() - t0, extra.cached ? 1 : 0, extra.tin || 0, extra.tout || 0).run().catch(() => { }));
  // 같은 문장(같은 사전 버전)은 저장해 둔 결과 — 횟수에 안 셈
  if (Math.random() < 0.02) ctx.waitUntil(env.DB.prepare('DELETE FROM ai_log WHERE ts<?').bind(t0 - 365 * DAY).run().catch(() => { }));   // 기록은 1년 보관 (개인정보처리방침)
  const hit = who === 'eval' ? null : await env.DB.prepare('SELECT res FROM ai_cache WHERE qh=? AND ts>?').bind(qh, t0 - 7 * DAY).first();   // 평가는 늘 새로
  if (hit) { const res = JSON.parse(hit.res); log(res, { cached: true }); return send({ ...res, cached: true }); }
  const limit = who === 'eval' ? 1e9 : +(who.startsWith('u:') ? env.AI_LIMIT_USER || 30 : env.AI_LIMIT_ANON || 10);
  const used = (await env.DB.prepare('SELECT COUNT(*) n FROM ai_log WHERE day=? AND who=? AND cached=0').bind(day, who).first()).n;
  if (used >= limit) return send({ error: 'limit', limit, login: !who.startsWith('u:') }, 429);
  let raw = null, usage = {}, tries = 0;
  while (!raw && tries < 2) {
    tries++;
    const r = await claude(env, cat, q);
    usage = r.usage; raw = parseJSON(r.text);
  }
  if (!raw) return send({ error: 'parse' }, 502);
  const res = validate(raw, cat);
  ctx.waitUntil(env.DB.prepare('INSERT OR REPLACE INTO ai_cache (qh, res, ts) VALUES (?,?,?)').bind(qh, JSON.stringify(res), t0).run().catch(() => { }));
  log(res, { tin: (usage.input_tokens || 0) + (usage.cache_read_input_tokens || 0) + (usage.cache_creation_input_tokens || 0), tout: usage.output_tokens || 0 });
  return send({ ...res, left: limit - used - 1 });
}

export async function whoOf(req, env, getSession) {
  if (env.ALERT_KEY && req.headers.get('x-ai-eval') === env.ALERT_KEY) return 'eval';     // 평가 워크플로(.github/workflows/ai-eval.yml) — 횟수 제한·저장 결과 없이
  try {
    const s = await getSession();
    if (s && s.user) return 'u:' + s.user.id;
  } catch (e) { }
  const ip = req.headers.get('cf-connecting-ip') || '0';
  return 'ip:' + (await sha(ip + '|' + today() + '|' + (env.ALERT_KEY || 'salt'))).slice(0, 20);
}
