// 티커맵 API — Cloudflare Worker + D1
//
// 하는 일
//   1) 후보함 동기화: 브라우저 localStorage ↔ D1 (기기코드 = 로그인 전 단계의 계정 역할)
//   2) 텔레그램 봇: /start <토큰>으로 후보함과 대화방 연결, /상태 /끄기 /켜기 /기기 /도움말
//   3) 알림 발송 창구: GitHub Actions(hub alerts)가 구독자 목록을 받아 가고, 만든 메시지를 여기로 보내면 텔레그램으로 전달
//      → 봇 토큰은 이 Worker에만 있음
//
// 설정 (Settings → Bindings / Variables and Secrets)
//   D1 바인딩     DB          → tickermap 데이터베이스
//   Secret       BOT_TOKEN   → BotFather가 준 봇 토큰
//   Secret       ALERT_KEY   → 아무 긴 무작위 문자열 (GitHub Secrets의 ALERT_KEY와 같은 값)
//   Variable     SITE        → 사이트 주소 (기본 https://flytothejy.github.io/market-data/hub)
// 처음 한 번:  https://<이 Worker 주소>/setup?key=<ALERT_KEY>  → 텔레그램 웹훅·명령어 등록

import { makeAuth, log, isNoEmail, SITE_ORIGINS } from './auth.js';
import { admin, adminCors, ADMIN_ORIGINS } from './admin.js';
import { aiScreen, whoOf } from './ai.js';

const DAY = 864e5;
const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*' },
});
const CORS = {
  'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': 'content-type', 'access-control-max-age': '86400',
};
const rnd = (n = 24) => {
  const a = crypto.getRandomValues(new Uint8Array(n));
  return btoa(String.fromCharCode(...a)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};
async function sha(s) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}
const site = env => (env.SITE || 'https://flytothejy.github.io/market-data/hub').replace(/\/$/, '');
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// ---- 텔레그램
async function tg(env, method, body) {
  try {
  const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  });
  return { status: r.status, body: await r.json().catch(() => ({})) };
  } catch (e) { return { status: 0, body: { description: String(e && e.message || e) } }; }
}
let _bot = null;
async function botName(env) {
  if (_bot) return _bot;
  const r = await tg(env, 'getMe', {});
  _bot = r.body && r.body.result && r.body.result.username;
  return _bot;
}
const say = (env, chat, text) => tg(env, 'sendMessage', { chat_id: chat, text, parse_mode: 'HTML', disable_web_page_preview: true });

// ---- 기기코드 → 사용자
async function userOf(env, code) {
  if (!code || code.length < 20) return null;
  const h = await sha(code);
  const d = await env.DB.prepare('SELECT uid FROM devices WHERE code_hash=?').bind(h).first();
  if (!d) return null;
  const now = Date.now();
  await env.DB.prepare('UPDATE devices SET seen=? WHERE code_hash=?').bind(now, h).run();
  return await env.DB.prepare('SELECT * FROM users WHERE uid=?').bind(d.uid).first();
}
async function newDevice(env, uid) {
  const code = rnd(24), now = Date.now();
  await env.DB.prepare('INSERT INTO devices (code_hash, uid, created, seen) VALUES (?,?,?,?)').bind(await sha(code), uid, now, now).run();
  return code;
}
async function newToken(env, uid, kind) {
  const token = rnd(18);
  await env.DB.batch([
    env.DB.prepare('DELETE FROM tokens WHERE exp < ?').bind(Date.now()),
    env.DB.prepare('INSERT INTO tokens (token, uid, kind, exp) VALUES (?,?,?,?)').bind(token, uid, kind, Date.now() + 10 * 60e3),
  ]);
  return token;
}
async function useToken(env, token, kind) {
  if (!token) return null;
  const r = await env.DB.prepare('SELECT * FROM tokens WHERE token=? AND kind=?').bind(token, kind).first();
  if (!r) return null;
  await env.DB.prepare('DELETE FROM tokens WHERE token=?').bind(token).run();
  return r.exp >= Date.now() ? r.uid : null;
}
async function wipe(env, uid) {                       // 서버에 있는 이 사용자의 모든 것 (후보함·기기·연결 토큰·텔레그램 연결)
  await env.DB.batch([
    env.DB.prepare('DELETE FROM watch WHERE uid=?').bind(uid),
    env.DB.prepare('DELETE FROM portfolio WHERE uid=?').bind(uid),
    env.DB.prepare('DELETE FROM devices WHERE uid=?').bind(uid),
    env.DB.prepare('DELETE FROM tokens WHERE uid=?').bind(uid),
    env.DB.prepare('DELETE FROM users WHERE uid=?').bind(uid),
  ]);
}
const me = u => ({ linked: !!u.chat_id, tg: u.tg_name || null, mode: u.mode || 'digest' });

// ---- 후보함 병합: 항목마다 u(수정 시각, ms)가 더 큰 쪽이 이김
const TICK = /^[A-Z0-9.\-^]{1,12}$/;
async function doc(env, uid) {
  const r = await env.DB.prepare('SELECT data FROM watch WHERE uid=?').bind(uid).first();
  try { return r ? JSON.parse(r.data) : []; } catch (e) { return []; }
}
async function merge(env, uid, items) {
  const cur = await doc(env, uid), by = Object.fromEntries(cur.map(x => [x.t, x]));
  let changed = false;
  for (const it of (items || []).slice(0, 400)) {
    if (!it || typeof it.t !== 'string' || !TICK.test(it.t)) continue;
    const u = Math.floor(+it.u || 0), old = by[it.t];
    if (old && !(u > old.u)) continue;
    let x = it.del ? { t: it.t, u, del: 1 } : { ...it, u };
    if (!x.del && JSON.stringify(x).length > 6000) x = { ...x, snap: null };   // 너무 큰 스냅샷은 버림
    by[it.t] = x; changed = true;
  }
  // 지운 표시는 90일 지나면 정리
  const all = Object.values(by).filter(x => !x.del || x.u > Date.now() - 90 * DAY).slice(0, 600);
  if (changed) await env.DB.prepare('INSERT INTO watch (uid, data, u) VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET data=excluded.data, u=excluded.u').bind(uid, JSON.stringify(all), Date.now()).run();
  return all;
}
const live = a => a.filter(x => !x.del);

// ---- 종목별 이용 집계 (개인 식별 없음: 날짜·종목·종류·횟수만. 기기·IP는 저장하지 않음)
// 종류: v 종목 화면 조회 · w 후보함 담기 · c 비교에 추가 · a 알림 링크로 들어옴
// 같은 기기·같은 종목·같은 종류는 하루 한 번만 보내도록 브라우저에서 거름 (부풀리기 방지는 그쪽 + 요청당 개수 제한)
const EV_KINDS = new Set(['v', 'w', 'c', 'a', 'u', 'p']);   // u 방문(기기·하루 한 번, t=SITE) · p 화면별 방문(t=화면 이름)
const kstDay = (ms = Date.now()) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10);
const OK_ORIGIN = /^(https:\/\/(([a-z0-9-]+\.)?tickermap\.kr|flytothejy\.github\.io|([a-z0-9-]+\.)?tickermap\.pages\.dev)|http:\/\/localhost(:\d+)?)$/;
async function events(req, env) {
  const o = req.headers.get('origin') || '';
  if (o && !OK_ORIGIN.test(o)) return new Response(null, { status: 204, headers: CORS });
  const ua = req.headers.get('user-agent') || '';
  if (/bot|crawl|spider|headless|preview|Yeti/i.test(ua)) return new Response(null, { status: 204, headers: CORS });
  let b = {};
  try { b = JSON.parse(await req.text()); } catch (e) { }
  const d = kstDay(), seen = new Set(), st = [];
  for (const x of (Array.isArray(b.e) ? b.e : []).slice(0, 20)) {
    if (!Array.isArray(x) || !EV_KINDS.has(x[0]) || typeof x[1] !== 'string' || !TICK.test(x[1])) continue;
    const key = x[0] + x[1]; if (seen.has(key)) continue; seen.add(key);
    st.push(env.DB.prepare('INSERT INTO stats (d, t, k, n) VALUES (?,?,?,1) ON CONFLICT(d, t, k) DO UPDATE SET n = n + 1').bind(d, x[1], x[0]));
  }
  if (st.length) await env.DB.batch(st);
  return new Response(null, { status: 204, headers: CORS });
}
async function popular(req, env, ctx) {
  // 최근 7일·30일 종목별 합계 — 10분 캐시
  const cache = caches.default, key = new Request(new URL('/api/popular', req.url).href);
  const hit = await cache.match(key);
  if (hit) return hit;
  const out = { asof: kstDay(), d7: {}, d30: {}, tot7: {} };
  const rows = (await env.DB.prepare('SELECT d, t, k, n FROM stats WHERE d >= ?').bind(kstDay(Date.now() - 29 * 864e5)).all()).results;
  const c7 = kstDay(Date.now() - 6 * 864e5);
  for (const r of rows) {
    if (r.k === 'u' || r.k === 'p') { if (r.d >= c7) out.tot7[r.k] = (out.tot7[r.k] || 0) + r.n; continue; }   // 방문 수는 종목 목록에 넣지 않음
    for (const [name, ok] of [['d30', true], ['d7', r.d >= c7]]) {
      if (!ok) continue;
      const m = out[name][r.t] = out[name][r.t] || {};
      m[r.k] = (m[r.k] || 0) + r.n;
    }
    if (r.d >= c7) out.tot7[r.k] = (out.tot7[r.k] || 0) + r.n;
  }
  const res = new Response(JSON.stringify(out), { headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*', 'cache-control': 'public, max-age=600' } });
  ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}

// ---- 포트폴리오: 문서 통째로, 수정 시각이 더 최근인 쪽이 이김
// v2 = 관심 포트폴리오 여러 개 { v:2, pfs:[{id, name, items:[{t, w}], start, cap, rb}], u } — 개수는 PF_MAX(기본 3)까지
function pfDoc(pf, env) {
  const max = Math.max(1, Math.min(20, +env.PF_MAX || 3)), day = /^\d{4}-\d{2}-\d{2}$/;
  const pfs = (Array.isArray(pf.pfs) ? pf.pfs : []).slice(0, max).filter(p => p && typeof p === 'object').map(p => ({
    id: String(p.id || rnd(6)).replace(/[^A-Za-z0-9]/g, '').slice(0, 12) || rnd(6),
    name: String(p.name || '포트폴리오').slice(0, 30),
    items: (Array.isArray(p.items) ? p.items : []).slice(0, 30).filter(x => x && TICK.test(x.t)).map(x => ({ t: x.t, w: Math.max(0, Math.min(100, +x.w || 0)) })),
    start: day.test(p.start) ? p.start : null,
    cap: Math.max(100, Math.min(1e9, +p.cap || 10000)),
    rb: ['q', 'y', 'band'].includes(p.rb) ? p.rb : 'none',
    why: String(p.why || '').slice(0, 80),
    hist: (Array.isArray(p.hist) ? p.hist : []).slice(-20).filter(h => h && day.test(h.d)).map(h => ({
      d: h.d, rb: ['q', 'y', 'band'].includes(h.rb) ? h.rb : 'none', why: String(h.why || '').slice(0, 80),
      items: (Array.isArray(h.items) ? h.items : []).slice(0, 30).filter(x => x && TICK.test(x.t)).map(x => ({ t: x.t, w: Math.max(0, Math.min(100, +x.w || 0)) })),
    })),
  }));
  return { v: 2, pfs, u: Math.floor(+pf.u) };
}
async function syncPf(env, uid, pf) {
  const cur = await env.DB.prepare('SELECT data, u FROM portfolio WHERE uid=?').bind(uid).first();
  if (pf && pf.v === 2 && (+pf.u || 0) > (cur ? cur.u : -1)) {
    const doc = pfDoc(pf, env);
    await env.DB.prepare('INSERT INTO portfolio (uid, data, u) VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET data=excluded.data, u=excluded.u').bind(uid, JSON.stringify(doc), doc.u).run();
    return doc;
  }
  return cur ? JSON.parse(cur.data) : null;
}
// 알림 대상: 관심 종목 + 포트폴리오 종목 (포트폴리오 이름을 붙여서)
function pfTickers(data) {
  let d = null; try { d = JSON.parse(data); } catch (e) { }
  const out = {};
  if (d && d.v === 2) for (const p of d.pfs || []) for (const x of p.items || []) if (x.w > 0) (out[x.t] = out[x.t] || []).push(p.name);
  return out;
}

// ---- 브라우저용 API
async function api(req, env, path) {
  const b = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  if (path === '/api/register') {                     // 이 브라우저를 새 사용자로
    const uid = rnd(12), now = Date.now();
    await env.DB.prepare('INSERT INTO users (uid, mode, created) VALUES (?,?,?)').bind(uid, 'digest', now).run();
    return json({ code: await newDevice(env, uid) });
  }
  if (path === '/api/join') {                         // 텔레그램 /기기 링크로 다른 기기 추가
    const uid = await useToken(env, b.token, 'dev');
    if (!uid) return json({ error: '링크가 만료됐거나 이미 쓰였어요. 텔레그램에서 /기기 를 다시 보내 주세요' }, 400);
    return json({ code: await newDevice(env, uid) });
  }
  const u = await userOf(env, b.code);
  if (!u) return json({ error: 'unknown device' }, 401);
  if (path === '/api/sync') {
    const out = { items: await merge(env, u.uid, b.items), me: me(u) };
    if (u.auth_id) out.pf = await syncPf(env, u.uid, b.pf);          // 포트폴리오는 로그인한 계정만
    return json(out);
  }
  if (path === '/api/me') return json({ me: me(u) });
  if (path === '/api/link') {                         // 텔레그램 연결 링크 (10분)
    const bot = await botName(env);
    if (!bot) return json({ error: '봇 설정이 아직이에요' }, 500);
    return json({ url: `https://t.me/${bot}?start=${await newToken(env, u.uid, 'tg')}` });
  }
  if (path === '/api/mode') {
    const mode = b.mode === 'off' ? 'off' : 'digest';
    await env.DB.prepare('UPDATE users SET mode=? WHERE uid=?').bind(mode, u.uid).run();
    return json({ me: { ...me(u), mode } });
  }
  if (path === '/api/delete') { await wipe(env, u.uid); return json({ deleted: true }); }
  if (path === '/api/unlink') {
    await env.DB.prepare('UPDATE users SET chat_id=NULL, tg_name=NULL WHERE uid=?').bind(u.uid).run();
    return json({ me: { ...me(u), linked: false, tg: null } });
  }
  return json({ error: 'not found' }, 404);
}

// ---- 계정 (쿠키 세션이 필요한 요청 — 허용한 사이트 주소에서만, 자격 증명 포함 CORS)
const credCors = (req, env) => {
  const o = req.headers.get('origin') || '';
  const ok = SITE_ORIGINS.includes(o) || ADMIN_ORIGINS.includes(o) || (env.AUTH_DEV === '1' && /^http:\/\/localhost(:\d+)?$/.test(o));
  return ok ? { 'access-control-allow-origin': o, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'vary': 'Origin' } : {};
};
// AI 문장 검색: 사이트·미리보기(*.tickermap.pages.dev)는 쿠키 포함 허용(로그인이면 횟수 더), 그 밖은 쿠키 없이
const aiCors = (req, env) => {
  const o = req.headers.get('origin') || '';
  const ok = SITE_ORIGINS.includes(o) || /^https:\/\/([a-z0-9-]+\.)?tickermap\.pages\.dev$/.test(o) || (env.AUTH_DEV === '1' && /^http:\/\/localhost(:\d+)?$/.test(o));
  return ok ? { 'access-control-allow-origin': o, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'POST,OPTIONS', 'vary': 'Origin' } : CORS;
};
const withCors = (res, h) => { const r = new Response(res.body, res); for (const [k, v] of Object.entries(h)) r.headers.set(k, v); return r; };
const cjson = (o, h, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', ...h } });

async function accUser(env, authId) { return await env.DB.prepare('SELECT * FROM users WHERE auth_id=?').bind(authId).first(); }

async function account(req, env, path) {
  const h = credCors(req, env);
  const auth = makeAuth(env);
  const s = await auth.api.getSession({ headers: req.headers, query: { disableCookieCache: true } });   // 계정 일은 늘 DB 기준 (삭제·로그아웃 직후 쿠키 캐시 무시)
  if (!s) return cjson({ error: 'login required' }, h, 401);
  const A = s.user, ua = req.headers.get('user-agent') || '';
  const b = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  if (path === '/api/account/me') {
    const u = await accUser(env, A.id);
    const prov = (await env.DB.prepare('SELECT providerId FROM account WHERE userId=?').bind(A.id).all()).results.map(r => r.providerId);
    const items = u ? live(await doc(env, u.uid)).length : 0;
    return cjson({ user: { name: A.name, email: isNoEmail(A.email) ? null : A.email, image: A.image, since: A.createdAt }, providers: prov, linked: !!u, tg: u ? { linked: !!u.chat_id, name: u.tg_name, mode: u.mode } : null, items }, h);
  }
  if (path === '/api/account/claim') {
    // 이 기기(기기코드)를 계정에 묶음. 계정에 이미 다른 기기 데이터가 있으면 후보함을 합침 (항목마다 최근 수정 우선)
    let acc = await accUser(env, A.id);
    const dev = b.code ? await userOf(env, b.code) : null;
    let code = b.code && dev ? b.code : null;
    if (!acc && dev) {
      await env.DB.prepare('UPDATE users SET auth_id=? WHERE uid=?').bind(A.id, dev.uid).run();
      acc = { ...dev, auth_id: A.id };
    } else if (acc && dev && dev.uid !== acc.uid) {
      if (dev.auth_id && dev.auth_id !== A.id) return cjson({ error: '이 기기는 다른 계정에 연결돼 있어요. 그 계정에서 로그아웃한 뒤 다시 시도해 주세요' }, h, 409);
      await merge(env, acc.uid, await doc(env, dev.uid));
      const st = [env.DB.prepare('UPDATE devices SET uid=? WHERE uid=?').bind(acc.uid, dev.uid)];
      if (!acc.chat_id && dev.chat_id) st.push(env.DB.prepare('UPDATE users SET chat_id=?, tg_name=?, linked=?, mode=? WHERE uid=?').bind(dev.chat_id, dev.tg_name, dev.linked, dev.mode, acc.uid));
      const dpf = await env.DB.prepare('SELECT data, u FROM portfolio WHERE uid=?').bind(dev.uid).first();
      if (dpf) await syncPf(env, acc.uid, { ...JSON.parse(dpf.data), u: dpf.u });
      st.push(env.DB.prepare('DELETE FROM portfolio WHERE uid=?').bind(dev.uid));
      st.push(env.DB.prepare('DELETE FROM watch WHERE uid=?').bind(dev.uid), env.DB.prepare('DELETE FROM tokens WHERE uid=?').bind(dev.uid), env.DB.prepare('DELETE FROM users WHERE uid=?').bind(dev.uid));
      await env.DB.batch(st);
    } else if (!acc) {
      const uid = rnd(12);
      await env.DB.prepare('INSERT INTO users (uid, mode, created, auth_id) VALUES (?,?,?,?)').bind(uid, 'digest', Date.now(), A.id).run();
      acc = { uid };
    }
    if (!code) code = await newDevice(env, acc.uid);
    await log(env, A.id, 'device_link', ua);
    return cjson({ code }, h);
  }
  if (path === '/api/account/forget-device') {          // 로그아웃할 때: 이 기기코드를 계정에서 떼어 냄 (이 기기에선 더 이상 계정 후보함을 못 받음)
    if (b.code) await env.DB.prepare('DELETE FROM devices WHERE code_hash=?').bind(await sha(b.code)).run();
    await log(env, A.id, 'logout', ua);
    return cjson({ ok: true }, h);
  }
  if (path === '/api/account/prefs') {                  // 설정: GET 읽기 · POST {data, u} — 서버 것보다 최근이면 저장, 늘 최신을 돌려줌
    const cur = await env.DB.prepare('SELECT data, u FROM prefs WHERE auth_id=?').bind(A.id).first();
    if (req.method === 'POST' && b && typeof b.data === 'object' && b.data && +b.u > (cur ? cur.u : 0)) {
      const data = JSON.stringify(b.data).slice(0, 8000);
      await env.DB.prepare('INSERT INTO prefs (auth_id, data, u) VALUES (?,?,?) ON CONFLICT(auth_id) DO UPDATE SET data=excluded.data, u=excluded.u').bind(A.id, data, +b.u).run();
      return cjson({ data: JSON.parse(data), u: +b.u }, h);
    }
    return cjson(cur ? { data: JSON.parse(cur.data), u: cur.u } : { data: null, u: 0 }, h);
  }
  if (path === '/api/account/log') {
    const rows = (await env.DB.prepare('SELECT ev, ua, at FROM auth_log WHERE auth_id=? ORDER BY at DESC LIMIT 30').bind(A.id).all()).results;
    return cjson({ log: rows }, h);
  }
  if (path === '/api/account/delete') {                 // 계정 탈퇴: 후보함·기기·텔레그램 연결·로그인 계정 모두 삭제
    const out = await auth.api.signOut({ headers: req.headers, asResponse: true }).catch(() => null);   // 쿠키 지우기
    const u = await accUser(env, A.id);
    if (u) await wipe(env, u.uid);
    await env.DB.batch([
      env.DB.prepare('DELETE FROM prefs WHERE auth_id=?').bind(A.id),
      env.DB.prepare('DELETE FROM ai_log WHERE who=?').bind('u:' + A.id),        // 문장으로 찾기 기록
      env.DB.prepare('DELETE FROM session WHERE userId=?').bind(A.id),
      env.DB.prepare('DELETE FROM account WHERE userId=?').bind(A.id),
      env.DB.prepare('DELETE FROM "user" WHERE id=?').bind(A.id),
    ]);
    await log(env, A.id, 'account_deleted', '');
    const res = cjson({ deleted: true }, h);
    if (out) for (const c of out.headers.getSetCookie ? out.headers.getSetCookie() : []) res.headers.append('set-cookie', c);
    return res;
  }
  return cjson({ error: 'not found' }, h, 404);
}

// ---- 텔레그램 웹훅
const HELP = s => `<b>티커맵 알림</b>
후보함 종목에 새 일이 생기면 매일 아침(한국 시간 8~9시) 한 번에 모아 보내요.
· 실적 발표 하루 전 · 실적 발표 후 주가 반응
· 종목 점검표에 새로 생긴 경고
· 임원 장내 매수

/상태 — 연결된 후보함 보기
/끄기 · /켜기 — 알림 멈춤·다시 받기
/기기 — 다른 기기(휴대폰·PC)에서 같은 후보함 쓰기
/해제 — 이 대화방 연결 끊기
/삭제 — 서버에 있는 내 데이터 모두 지우기

후보함: ${s}/watch.html
개인정보처리방침: ${s}/privacy.html
점수나 추천이 아니라 확인할 거리를 알려 드려요.`;

async function webhook(req, env) {
  if (req.headers.get('x-telegram-bot-api-secret-token') !== (await sha(env.ALERT_KEY + ':tg')).slice(0, 48)) return new Response('no', { status: 403 });
  const up = await req.json().catch(() => ({}));
  const m = up.message;
  if (!m || !m.chat || m.chat.type !== 'private' || typeof m.text !== 'string') return new Response('ok');
  const chat = m.chat.id, text = m.text.trim(), S = site(env);
  const [cmd0, arg] = text.split(/\s+/, 2);
  const cmd = cmd0.replace(/@.*$/, '');
  const user = await env.DB.prepare('SELECT * FROM users WHERE chat_id=?').bind(chat).first();
  const name = [m.from && m.from.first_name, m.from && m.from.last_name].filter(Boolean).join(' ') || (m.from && m.from.username) || '';

  if (cmd === '/start' && arg) {
    const uid = await useToken(env, arg, 'tg');
    if (!uid) { await say(env, chat, '연결 링크가 만료됐어요 (10분). 사이트 후보함에서 <b>텔레그램 연결</b>을 다시 눌러 주세요.'); return new Response('ok'); }
    // 이 대화방이 다른 후보함에 붙어 있었으면 떼고 새로 연결
    await env.DB.batch([
      env.DB.prepare('UPDATE users SET chat_id=NULL, tg_name=NULL WHERE chat_id=? AND uid<>?').bind(chat, uid),
      env.DB.prepare("UPDATE users SET chat_id=?, tg_name=?, linked=?, mode='digest' WHERE uid=?").bind(chat, name, Date.now(), uid),
    ]);
    await say(env, chat, `연결됐어요 ✅ 후보함 ${live(await doc(env, uid)).length}종목\n\n` + HELP(S));
    return new Response('ok');
  }
  if (!user) {
    await say(env, chat, `아직 후보함과 연결되지 않았어요.\n사이트 후보함에서 <b>텔레그램 연결</b>을 눌러 주세요.\n${S}/watch.html`);
    return new Response('ok');
  }
  if (cmd === '/상태' || cmd === '/status') {
    const rows = live(await doc(env, user.uid)).sort((a, b) => b.u - a.u);
    const P = { hold: '보유', consider: '고민', watch: '관찰' };
    const list = rows.slice(0, 60).map(d => `${esc(d.t)}${P[d.purpose] ? `(${P[d.purpose]})` : ''}`).join(' · ') + (rows.length > 60 ? ' …' : '');
    await say(env, chat, `알림 ${user.mode === 'off' ? '<b>꺼짐</b> (/켜기)' : '<b>켜짐</b> — 매일 아침 묶음'}\n후보함 ${rows.length}종목\n${list || '(비어 있음)'}\n\n${S}/watch.html`);
  } else if (cmd === '/끄기' || cmd === '/off' || cmd === '/stop') {
    await env.DB.prepare("UPDATE users SET mode='off' WHERE uid=?").bind(user.uid).run();
    await say(env, chat, '알림을 멈췄어요. 다시 받으려면 /켜기');
  } else if (cmd === '/켜기' || cmd === '/on') {
    await env.DB.prepare("UPDATE users SET mode='digest' WHERE uid=?").bind(user.uid).run();
    await say(env, chat, '알림을 다시 켰어요. 매일 아침 후보함 소식을 모아 보낼게요.');
  } else if (cmd === '/기기' || cmd === '/device') {
    const tok = await newToken(env, user.uid, 'dev');
    await say(env, chat, `다른 기기에서 아래 링크를 열면 같은 후보함이 이어져요 (10분 안에, 한 번만).\n${S}/watch.html#join=${tok}\n\n링크는 다른 사람에게 보내지 마세요.`);
  } else if (cmd === '/삭제' || cmd === '/delete') {
    if (arg !== '확인') await say(env, chat, '서버에 있는 후보함·연결 정보를 모두 지워요 (되돌릴 수 없음). 각 브라우저에 저장된 후보함은 그대로 남아요.\n지우려면 <b>/삭제 확인</b> 을 보내 주세요.');
    else { await wipe(env, user.uid); await say(env, chat, '모두 지웠어요. 이 대화방에 더는 알림을 보내지 않아요.'); }
  } else if (cmd === '/해제' || cmd === '/unlink') {
    await env.DB.prepare('UPDATE users SET chat_id=NULL, tg_name=NULL WHERE uid=?').bind(user.uid).run();
    await say(env, chat, '연결을 끊었어요. 후보함은 사이트에 그대로 있어요.');
  } else {
    await say(env, chat, HELP(S));
  }
  return new Response('ok');
}

// ---- Actions(알림 엔진)용 — Authorization: Bearer ALERT_KEY
async function internal(req, env, path) {
  if (!env.ALERT_KEY || req.headers.get('authorization') !== `Bearer ${env.ALERT_KEY}`) return json({ error: 'forbidden' }, 403);
  if (path === '/internal/subs') {
    await env.DB.prepare('DELETE FROM auth_log WHERE at < ?').bind(Date.now() - 365 * DAY).run().catch(() => { });
    await env.DB.prepare('DELETE FROM alert_log WHERE at < ?').bind(Date.now() - 90 * DAY).run().catch(() => { });
    await env.DB.prepare('DELETE FROM admin_audit WHERE at < ?').bind(Date.now() - 730 * DAY).run().catch(() => { });   // 보안 기록은 1년 보관 (매일 아침 알림 때 정리)                    // 알림 받을 사용자와 후보함 (필요한 필드만)
    const rows = (await env.DB.prepare("SELECT u.uid, w.data, p.data pdata FROM users u LEFT JOIN watch w ON w.uid=u.uid LEFT JOIN portfolio p ON p.uid=u.uid WHERE u.chat_id IS NOT NULL AND u.mode<>'off'").all()).results;
    const users = rows.map(r => {
      let a = []; try { a = JSON.parse(r.data || '[]'); } catch (e) { }
      const pt = r.pdata ? pfTickers(r.pdata) : {};
      const items = live(a).map(d => ({ t: d.t, purpose: d.purpose || '', at: d.at || null, px: d.px ?? null, pf: pt[d.t] || [] }));
      for (const t of Object.keys(pt)) if (!items.some(x => x.t === t)) items.push({ t, purpose: '', at: null, px: null, pf: pt[t] });
      return { uid: r.uid, items };
    }).filter(u => u.items.length);
    return json({ users });
  }
  if (path === '/internal/ops') {                       // 운영 지표 (매일 아침 운영 알림용) — 사람별이 아니라 합계만
    const day = kstDay(), yd = kstDay(Date.now() - 864e5), d7 = kstDay(Date.now() - 6 * 864e5);
    const one = async (q, ...b) => (await env.DB.prepare(q).bind(...b).first()) || {};
    const sinceMs = Date.parse(yd + 'T00:00:00+09:00');
    const acc = await one('SELECT COUNT(*) n FROM "user"').catch(() => ({}));
    const accNew = await one('SELECT COUNT(*) n FROM "user" WHERE createdAt >= ?', new Date(sinceMs).toISOString()).catch(() => ({}));
    const prov = (await env.DB.prepare('SELECT providerId p, COUNT(*) n FROM account GROUP BY providerId').all().catch(() => ({ results: [] }))).results;
    const us = await one("SELECT COUNT(*) n, SUM(chat_id IS NOT NULL) tg, SUM(chat_id IS NOT NULL AND mode='off') tg_off, SUM(auth_id IS NOT NULL) linked FROM users");
    const wl = (await env.DB.prepare('SELECT data FROM watch').all()).results.map(r => { try { return JSON.parse(r.data).filter(x => !x.del).length; } catch (e) { return 0; } }).filter(n => n > 0);
    const st = (await env.DB.prepare('SELECT d, k, SUM(n) n FROM stats WHERE d >= ? GROUP BY d, k').bind(d7).all()).results;
    const sum = (d, k) => st.filter(r => (d === '7' ? true : r.d === d) && r.k === k).reduce((a, r) => a + r.n, 0);
    const logins = await one('SELECT COUNT(*) n FROM auth_log WHERE ev=? AND at >= ?', 'login', sinceMs).catch(() => ({}));
    return json({
      day, yesterday: yd,
      accounts: acc.n || 0, accounts_new: accNew.n || 0, providers: Object.fromEntries(prov.map(r => [r.p, r.n])),
      users: us.n || 0, telegram: us.tg || 0, telegram_off: us.tg_off || 0, linked: us.linked || 0,
      watch_users: wl.length, watch_avg: wl.length ? +(wl.reduce((a, b) => a + b, 0) / wl.length).toFixed(1) : 0,
      visits_y: sum(yd, 'u'), visits_7: sum('7', 'u'), views_y: sum(yd, 'v'), adds_y: sum(yd, 'w'), logins_y: logins.n || 0,
      pages_y: Object.fromEntries((await env.DB.prepare("SELECT t, n FROM stats WHERE d=? AND k='p' ORDER BY n DESC").bind(yd).all()).results.map(r => [r.t, r.n])),
    });
  }
  if (path === '/internal/send') {                    // { msgs: [{uid, text}] } — 한 번에 15개까지 (무료 요금제 요청당 외부 호출 50개 제한)
    const b = await req.json().catch(() => ({}));
    const out = [];
    for (const m of (b.msgs || []).slice(0, 15)) {
      const u = await env.DB.prepare('SELECT chat_id FROM users WHERE uid=?').bind(m.uid).first();
      if (!u || !u.chat_id) { out.push({ uid: m.uid, ok: false, why: 'unlinked' }); continue; }
      const r = await say(env, u.chat_id, String(m.text).slice(0, 4096));
      if (r.status === 403) await env.DB.prepare('UPDATE users SET chat_id=NULL WHERE uid=?').bind(m.uid).run();   // 봇 차단
      out.push({ uid: m.uid, ok: r.status === 200, why: r.status === 200 ? '' : String(r.body && r.body.description || r.status) });
      const head = String(m.text).replace(/<[^>]+>/g, '').split('\n').filter(Boolean).slice(0, 2).join(' / ').slice(0, 140);
      await env.DB.prepare('INSERT INTO alert_log (uid, kind, ok, why, head, at) VALUES (?,?,?,?,?,?)').bind(m.uid, String(m.kind || 'alert').slice(0, 20), r.status === 200 ? 1 : 0, out[out.length - 1].why.slice(0, 200), head, Date.now()).run().catch(() => { });
    }
    return json({ results: out });
  }
  return json({ error: 'not found' }, 404);
}

async function setup(req, env) {
  const u = new URL(req.url);
  if (!env.ALERT_KEY || u.searchParams.get('key') !== env.ALERT_KEY) return new Response('key가 맞지 않아요\n', { status: 403 });
  const hook = await tg(env, 'setWebhook', {
    url: `${u.origin}/tg`, secret_token: (await sha(env.ALERT_KEY + ':tg')).slice(0, 48),
    allowed_updates: ['message'], drop_pending_updates: true,
  });
  const cmds = await tg(env, 'setMyCommands', {
    commands: [
      { command: 'status', description: '연결된 후보함 보기 (/상태)' },
      { command: 'off', description: '알림 멈추기 (/끄기)' },
      { command: 'on', description: '알림 다시 받기 (/켜기)' },
      { command: 'device', description: '다른 기기에서 같은 후보함 쓰기 (/기기)' },
      { command: 'unlink', description: '이 대화방 연결 끊기 (/해제)' },
      { command: 'delete', description: '서버에 있는 내 데이터 모두 지우기 (/삭제)' },
      { command: 'help', description: '도움말' },
    ],
  });
  await tg(env, 'setMyDescription', { description: '티커맵 후보함 종목의 실적·점검표 경고·임원 매수를 매일 아침 모아 알려 드려요. 사이트 후보함에서 연결해 주세요.' });
  let db = 'ok';
  try { await env.DB.prepare('SELECT COUNT(*) FROM users').first(); } catch (e) { db = '테이블 없음 — schema.sql을 D1 Console에서 실행해 주세요'; }
  return new Response(`웹훅: ${hook.body.ok ? '등록됨' : '실패 ' + (hook.body.description || hook.status)}\n명령어: ${cmds.body.ok ? '등록됨' : '실패'}\n봇: @${await botName(env) || '?'}\nD1: ${db}\n`, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
}

export default {
  async fetch(req, env, ctx) {
    const path = new URL(req.url).pathname.replace(/\/$/, '') || '/';
    const cred = path.startsWith('/api/auth/') || path.startsWith('/api/account/');
    if (req.method === 'OPTIONS') return new Response(null, { headers: path.startsWith('/admin/') ? adminCors(req, env) : path === '/ai/screen' ? { ...aiCors(req, env), 'access-control-max-age': '86400' } : cred ? { ...credCors(req, env), 'access-control-max-age': '86400' } : CORS });
    try {
      if (path.startsWith('/api/auth/')) return withCors(await makeAuth(env).handler(req), credCors(req, env));
      if (path.startsWith('/admin/')) return await admin(req, env, path);
      if (path.startsWith('/api/account/')) return await account(req, env, path);
      if (path === '/ai/screen' && req.method === 'POST') {
        const h = aiCors(req, env);
        try {
          const who = await whoOf(req, env, () => makeAuth(env).api.getSession({ headers: req.headers }));
          return await aiScreen(req, env, ctx, who, h);
        } catch (e) { return new Response(JSON.stringify({ error: 'fail', detail: String(e && e.message || e).slice(0, 200) }), { status: 500, headers: { 'content-type': 'application/json', ...h } }); }
      }
      if (path === '/api/ev' && req.method === 'POST') return await events(req, env);
      if (path === '/api/popular' && req.method === 'GET') return await popular(req, env, ctx);
      if (path.startsWith('/api/') && req.method === 'POST') return await api(req, env, path);
      if (path === '/tg' && req.method === 'POST') return await webhook(req, env);
      if (path.startsWith('/internal/')) return await internal(req, env, path);
      if (path === '/setup') return await setup(req, env);
      return new Response(`tickermap api\nD1: ${env.DB ? '연결됨' : '없음'} · 봇 토큰: ${env.BOT_TOKEN ? '있음' : '없음'} · ALERT_KEY: ${env.ALERT_KEY ? '있음' : '없음'}\n`, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
    } catch (e) {
      return json({ error: String(e && e.message || e) }, 500);
    }
  },
};
