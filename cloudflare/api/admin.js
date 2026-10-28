// ---- 관리자 API (admin.tickermap.kr 전용)
// 잠금 두 겹: ① admin.tickermap.kr 주소 자체는 Cloudflare Access(이메일 인증)로 막고
//            ② 여기서 다시 로그인 세션 + 관리자 이메일 목록(ADMIN_EMAILS, Cloudflare 변수 — 쉼표로 여러 개) 확인
// 관리자가 부른 모든 요청은 admin_audit에 남김. 1단계는 보기 전용 (조치 기능 없음)
import { makeAuth, isNoEmail } from './auth.js';

export const ADMIN_ORIGINS = ['https://admin.tickermap.kr'];
const DAY = 864e5;
const kstDay = (ms = Date.now()) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10);
export const mask = e => {
  if (!e || isNoEmail(e)) return null;
  const [a, d] = e.split('@');
  return (a.length <= 3 ? a[0] + '**' : a.slice(0, 3) + '*'.repeat(Math.min(a.length - 3, 5))) + '@' + d;
};
const uaShort = ua => {
  if (!ua) return '';
  const os = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Mac OS X/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : '기타';
  const br = /KAKAOTALK/.test(ua) ? '카카오톡' : /NAVER/.test(ua) ? '네이버앱' : /Edg\//.test(ua) ? 'Edge' : /SamsungBrowser/.test(ua) ? '삼성 인터넷' : /CriOS|Chrome\//.test(ua) ? 'Chrome' : /Firefox|FxiOS/.test(ua) ? 'Firefox' : /Safari/.test(ua) ? 'Safari' : '기타';
  return `${os} · ${br}`;
};

export const adminCors = (req, env) => {
  const o = req.headers.get('origin') || '';
  const ok = ADMIN_ORIGINS.includes(o) || (env.AUTH_DEV === '1' && /^http:\/\/localhost(:\d+)?$/.test(o));
  return ok ? { 'access-control-allow-origin': o, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'vary': 'Origin', 'cache-control': 'no-store' } : { 'cache-control': 'no-store' };
};
const out = (o, h, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json; charset=utf-8', ...h } });
const all = async (env, q, ...b) => (await env.DB.prepare(q).bind(...b).all()).results;
const one = async (env, q, ...b) => (await env.DB.prepare(q).bind(...b).first()) || {};

export async function admin(req, env, path) {
  const h = adminCors(req, env);
  const s = await makeAuth(env).api.getSession({ headers: req.headers, query: { disableCookieCache: true } }).catch(() => null);
  if (!s) return out({ error: 'login required' }, h, 401);
  const allow = String(env.ADMIN_EMAILS || '').toLowerCase().split(',').map(x => x.trim()).filter(Boolean);
  const me = String(s.user.email || '').toLowerCase();
  if (!allow.length || !allow.includes(me)) return out({ error: 'not admin', email: mask(s.user.email) }, h, 403);
  const u = new URL(req.url), q = k => u.searchParams.get(k) || '';
  const audit = target => env.DB.prepare('INSERT INTO admin_audit (admin, action, target, at) VALUES (?,?,?,?)').bind(me, path.replace('/admin/', ''), target ? String(target).slice(0, 120) : null, Date.now()).run().catch(() => { });

  if (path === '/admin/me') return out({ email: s.user.email, name: s.user.name }, h);

  if (path === '/admin/overview') {
    await audit();
    const days = Math.min(+q('days') || 30, 90), from = kstDay(Date.now() - (days - 1) * DAY), fromMs = Date.parse(from + 'T00:00:00+09:00');
    const series = await all(env, "SELECT d, k, SUM(n) n FROM stats WHERE d >= ? AND k IN ('u','v','w','c','a') GROUP BY d, k", from);
    const toMs = v => typeof v === 'number' ? v : /^\d+$/.test(String(v)) ? +v : Date.parse(v);   // 저장 형식(숫자/문자열)에 상관없이
    const sg = {};
    for (const r of await all(env, 'SELECT createdAt FROM "user"')) { const t = toMs(r.createdAt); if (t >= fromMs) { const d = kstDay(t); sg[d] = (sg[d] || 0) + 1; } }
    const signups2 = Object.entries(sg).map(([d, n]) => ({ d, n }));
    const logins = await all(env, "SELECT CAST((at + 32400000) / 86400000 AS INTEGER) dd, COUNT(*) n, COUNT(DISTINCT auth_id) uu FROM auth_log WHERE ev='login' AND at >= ? GROUP BY dd", fromMs);
    const c7 = kstDay(Date.now() - 6 * DAY);
    const top = async k => all(env, 'SELECT t, SUM(n) n FROM stats WHERE d >= ? AND k = ? GROUP BY t ORDER BY n DESC LIMIT 15', c7, k);
    const now = Date.now();
    const tot = {
      accounts: (await one(env, 'SELECT COUNT(*) n FROM "user"')).n || 0,
      providers: Object.fromEntries((await all(env, 'SELECT providerId p, COUNT(*) n FROM account GROUP BY providerId')).map(r => [r.p, r.n])),
      ...(await one(env, "SELECT COUNT(*) users, SUM(chat_id IS NOT NULL) tg, SUM(chat_id IS NOT NULL AND mode='off') tg_off, SUM(auth_id IS NOT NULL) linked FROM users")),
      ...(await one(env, 'SELECT COUNT(*) devices, SUM(seen >= ?) dev7, SUM(seen >= ?) dev30 FROM devices', now - 7 * DAY, now - 30 * DAY)),
      pf_users: (await one(env, 'SELECT COUNT(*) n FROM portfolio')).n || 0,
      sessions: (await one(env, 'SELECT COUNT(*) n FROM session WHERE expiresAt > ?', now).catch(() => ({}))).n ?? null,
    };
    const wl = (await all(env, 'SELECT data FROM watch')).map(r => { try { return JSON.parse(r.data).filter(x => !x.del).length; } catch (e) { return 0; } }).filter(n => n > 0);
    tot.watch_users = wl.length; tot.watch_items = wl.reduce((a, b) => a + b, 0);
    const al = await one(env, 'SELECT COUNT(*) n, SUM(ok) ok FROM alert_log WHERE at >= ?', now - 7 * DAY).catch(() => ({}));
    return out({
      asof: kstDay(), days, from, series, tot, alerts7: { n: al.n || 0, ok: al.ok || 0 },
      signups: signups2, logins: logins.map(r => ({ d: new Date(r.dd * DAY).toISOString().slice(0, 10), n: r.n, uu: r.uu })),
      top_v: await top('v'), top_w: await top('w'), top_c: await top('c'),
      pages: await all(env, "SELECT t, SUM(n) n FROM stats WHERE d >= ? AND k = 'p' GROUP BY t ORDER BY n DESC", c7),
    }, h);
  }

  if (path === '/admin/users') {
    const term = q('q').trim(); await audit(term ? 'q=' + term : '');
    const off = Math.max(0, +q('offset') || 0);
    const where = term ? 'WHERE (u.email LIKE ? OR u.name LIKE ? OR u.id = ?)' : '';
    const b = term ? [`%${term}%`, `%${term}%`, term] : [];
    const rows = await all(env, `SELECT u.id, u.name, u.email, u.createdAt,
        (SELECT group_concat(providerId) FROM account a WHERE a.userId = u.id) prov,
        (SELECT MAX(at) FROM auth_log l WHERE l.auth_id = u.id AND l.ev = 'login') last_login,
        (SELECT COUNT(*) FROM session s WHERE s.userId = u.id AND s.expiresAt > ?) sess,
        x.uid, x.chat_id IS NOT NULL tg, x.mode, w.data wdata, p.data pdata,
        (SELECT COUNT(*) FROM devices dv WHERE dv.uid = x.uid) devs
      FROM "user" u LEFT JOIN users x ON x.auth_id = u.id LEFT JOIN watch w ON w.uid = x.uid LEFT JOIN portfolio p ON p.uid = x.uid
      ${where} ORDER BY u.createdAt DESC LIMIT 50 OFFSET ?`, Date.now(), ...b, off);
    const cnt = (s, f) => { try { const a = JSON.parse(s || '[]'); return f(a); } catch (e) { return 0; } };
    const anon = await one(env, 'SELECT COUNT(*) n, SUM(chat_id IS NOT NULL) tg FROM users WHERE auth_id IS NULL');
    return out({
      offset: off, anon: { n: anon.n || 0, tg: anon.tg || 0 },
      rows: rows.map(r => ({
        id: r.id, name: r.name, email: mask(r.email), created: typeof r.createdAt === 'number' ? r.createdAt : Date.parse(r.createdAt) || +r.createdAt, prov: (r.prov || '').split(',').filter(Boolean),
        last_login: r.last_login, sessions: r.sess, tg: !!r.tg, mode: r.mode, devices: r.devs || 0,
        watch: cnt(r.wdata, a => a.filter(x => !x.del).length), pf: cnt(r.pdata, a => (a.items || []).length),
      })),
    }, h);
  }

  if (path === '/admin/audit') {
    const ev = q('ev'), id = q('id'), before = +q('before') || Date.now() + 1;
    await audit([ev && 'ev=' + ev, id && 'id=' + id].filter(Boolean).join(' '));
    const cond = ['l.at < ?'], b = [before];
    if (ev) { cond.push('l.ev = ?'); b.push(ev); }
    if (id) { cond.push('l.auth_id = ?'); b.push(id); }
    const rows = await all(env, `SELECT l.id, l.auth_id, l.ev, l.ua, l.at, u.name, u.email FROM auth_log l LEFT JOIN "user" u ON u.id = l.auth_id WHERE ${cond.join(' AND ')} ORDER BY l.at DESC LIMIT 100`, ...b);
    const kinds = await all(env, 'SELECT ev, COUNT(*) n FROM auth_log WHERE at >= ? GROUP BY ev', Date.now() - 30 * DAY);
    return out({ kinds, rows: rows.map(r => ({ id: r.id, auth_id: r.auth_id, ev: r.ev, dev: uaShort(r.ua), at: r.at, name: r.name, email: mask(r.email), gone: !r.email })) }, h);
  }

  if (path === '/admin/alerts') {
    await audit();
    const before = +q('before') || Date.now() + 1;
    const rows = await all(env, 'SELECT id, uid, kind, ok, why, head, at FROM alert_log WHERE at < ? ORDER BY at DESC LIMIT 100', before).catch(() => []);
    const days = await all(env, 'SELECT CAST((at + 32400000) / 86400000 AS INTEGER) dd, COUNT(*) n, SUM(ok) ok, COUNT(DISTINCT uid) uu FROM alert_log WHERE at >= ? GROUP BY dd ORDER BY dd', Date.now() - 30 * DAY).catch(() => []);
    return out({ rows: rows.map(r => ({ ...r, uid: r.uid.slice(0, 4) + '…' })), days: days.map(r => ({ d: new Date(r.dd * DAY).toISOString().slice(0, 10), n: r.n, ok: r.ok, uu: r.uu })) }, h);
  }

  if (path === '/admin/ai') {                            // AI 문장 검색: 날짜별 합계 · 자주 나온 미지원 조건 · 최근 질문 (eval=1이면 평가 요청도)
    const withEval = q('eval') === '1', before = +q('before') || Date.now() + 1;
    await audit(withEval ? 'eval=1' : '');
    const ex = withEval ? '' : " AND who <> 'eval'";
    const since = Date.now() - 30 * DAY;
    const days = await all(env, `SELECT day d, COUNT(*) n, SUM(cached) cached, SUM(refused) refused, SUM(n = 0 AND refused = 0) empty, COUNT(DISTINCT who) uu,
        SUM(who LIKE 'u:%') login, SUM(tok_in) tin, SUM(tok_out) tout, AVG(CASE WHEN cached = 0 THEN ms END) ms FROM ai_log WHERE ts >= ?${ex} GROUP BY day ORDER BY day`, since).catch(() => []);
    const un = {};
    for (const r of await all(env, `SELECT unsup FROM ai_log WHERE ts >= ? AND unsup <> '[]'${ex}`, since).catch(() => []))
      try { for (const x of JSON.parse(r.unsup)) un[x] = (un[x] || 0) + 1; } catch (e) { }
    const rows = await all(env, `SELECT id, ts, who, q, res, n, unsup, refused, ms, cached, tok_in, tok_out FROM ai_log WHERE ts < ?${ex} ORDER BY ts DESC LIMIT 100`, before).catch(() => []);
    const kind = w => w === 'eval' ? '평가' : w.startsWith('u:') ? '로그인' : '비로그인';
    return out({
      days, unsup: Object.entries(un).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([t, n]) => ({ t, n })),
      rows: rows.map(r => { let x = {}; try { x = JSON.parse(r.res || '{}'); } catch (e) { }
        return { id: r.id, at: r.ts, who: kind(r.who), q: r.q, n: r.n, conds: (x.conds || []).map(c => c.k), sort: x.sort, assumptions: x.assumptions || [], unsupported: x.unsupported || [], refused: x.refused || null, ms: r.ms, cached: !!r.cached, tin: r.tok_in, tout: r.tok_out }; }),
    }, h);
  }

  if (path === '/admin/admin-log') {
    const rows = await all(env, 'SELECT admin, action, target, at FROM admin_audit ORDER BY at DESC LIMIT 200');
    return out({ rows: rows.map(r => ({ ...r, admin: mask(r.admin) })) }, h);
  }
  return out({ error: 'not found' }, h, 404);
}
