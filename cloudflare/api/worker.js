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
  if (path === '/api/sync') return json({ items: await merge(env, u.uid, b.items), me: me(u) });
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
  if (path === '/internal/subs') {                    // 알림 받을 사용자와 후보함 (필요한 필드만)
    const rows = (await env.DB.prepare("SELECT u.uid, w.data FROM users u JOIN watch w ON w.uid=u.uid WHERE u.chat_id IS NOT NULL AND u.mode<>'off'").all()).results;
    const users = rows.map(r => {
      let a = []; try { a = JSON.parse(r.data); } catch (e) { }
      return { uid: r.uid, items: live(a).map(d => ({ t: d.t, purpose: d.purpose || '', at: d.at || null, px: d.px ?? null })) };
    }).filter(u => u.items.length);
    return json({ users });
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
  async fetch(req, env) {
    const path = new URL(req.url).pathname.replace(/\/$/, '') || '/';
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });
    try {
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
