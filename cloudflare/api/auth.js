// 로그인 — Better Auth (구글·카카오·네이버). 세션은 tickermap.kr 전체에서 쓰는 쿠키(30일, 쓰면 하루 단위로 연장)
import { betterAuth } from 'better-auth';

export const SITE_ORIGINS = ['https://tickermap.kr', 'https://www.tickermap.kr'];
const noEmail = (p, id) => `${p}-${id}@users.noreply.tickermap.kr`;   // 이메일을 안 주는 경우(카카오 비즈 앱 아님 등)의 자리표시
export const isNoEmail = e => !e || e.endsWith('@users.noreply.tickermap.kr');

export async function log(env, authId, ev, ua) {
  try {
    await env.DB.prepare('INSERT INTO auth_log (auth_id, ev, ua, at) VALUES (?,?,?,?)').bind(authId, ev, (ua || '').slice(0, 160), Date.now()).run();
  } catch (e) { }
}

let cached = null, cachedFor = null;
export function makeAuth(env) {
  if (cached && cachedFor === env) return cached;
  const sp = {};
  if (env.GOOGLE_CLIENT_ID) sp.google = { clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET, prompt: 'select_account' };
  if (env.KAKAO_CLIENT_ID) sp.kakao = {
    clientId: env.KAKAO_CLIENT_ID, clientSecret: env.KAKAO_CLIENT_SECRET,
    disableDefaultScope: true, scope: ['profile_nickname', 'profile_image'],     // 이메일은 비즈 앱에서만 → 받지 않음
    mapProfileToUser: p => {
      const em = p.kakao_account && p.kakao_account.email;
      return { email: em || noEmail('kakao', p.id), emailVerified: !!em };
    },
  };
  if (env.NAVER_CLIENT_ID) sp.naver = {
    clientId: env.NAVER_CLIENT_ID, clientSecret: env.NAVER_CLIENT_SECRET,
    mapProfileToUser: p => { const r = p.response || {}; return { email: r.email || noEmail('naver', r.id), emailVerified: !!r.email }; },
  };
  cached = betterAuth({
    database: env.DB,
    secret: env.AUTH_SECRET,
    baseURL: env.API_URL || 'https://api.tickermap.kr',
    basePath: '/api/auth',
    trustedOrigins: [...SITE_ORIGINS, ...(env.AUTH_DEV === '1' ? ['http://localhost:8766'] : [])],
    socialProviders: sp,
    emailAndPassword: { enabled: env.AUTH_DEV === '1' },                         // 로컬 시험용만
    session: { expiresIn: 60 * 60 * 24 * 30, updateAge: 60 * 60 * 24, cookieCache: { enabled: true, maxAge: 300 } },
    account: { accountLinking: { enabled: true, trustedProviders: ['google', 'kakao', 'naver'] } },
    user: { deleteUser: { enabled: true } },
    advanced: {
      crossSubDomainCookies: env.AUTH_DEV === '1' ? { enabled: false } : { enabled: true, domain: 'tickermap.kr' },
      defaultCookieAttributes: env.AUTH_DEV === '1' ? { sameSite: 'lax', secure: false } : { sameSite: 'lax', secure: true },
      useSecureCookies: env.AUTH_DEV !== '1',
      ipAddress: { disableIpTracking: true },                                      // IP는 저장하지 않음
    },
    databaseHooks: {
      session: { create: { after: async s => { await log(env, s.userId, 'login', s.userAgent); } } },
    },
    telemetry: { enabled: false },
  });
  cachedFor = env;
  return cached;
}
