-- 로그인 (Better Auth 1.7 기본 테이블 — 이 버전의 getMigrations가 만든 그대로)
CREATE TABLE IF NOT EXISTS "user" ("id" text not null primary key, "name" text not null, "email" text not null unique, "emailVerified" integer not null, "image" text, "createdAt" date not null, "updatedAt" date not null);
CREATE TABLE IF NOT EXISTS "session" ("id" text not null primary key, "expiresAt" date not null, "token" text not null unique, "createdAt" date not null, "updatedAt" date not null, "ipAddress" text, "userAgent" text, "userId" text not null references "user" ("id") on delete cascade);
CREATE TABLE IF NOT EXISTS "account" ("id" text not null primary key, "accountId" text not null, "providerId" text not null, "userId" text not null references "user" ("id") on delete cascade, "accessToken" text, "refreshToken" text, "idToken" text, "accessTokenExpiresAt" date, "refreshTokenExpiresAt" date, "scope" text, "password" text, "createdAt" date not null, "updatedAt" date not null);
CREATE TABLE IF NOT EXISTS "verification" ("id" text not null primary key, "identifier" text not null, "value" text not null, "expiresAt" date not null, "createdAt" date not null, "updatedAt" date not null);
CREATE INDEX IF NOT EXISTS "session_userId_idx" on "session" ("userId");
CREATE INDEX IF NOT EXISTS "account_userId_idx" on "account" ("userId");
CREATE INDEX IF NOT EXISTS "verification_identifier_idx" on "verification" ("identifier");
-- 우리 사용자(후보함·텔레그램)와 로그인 계정 연결
ALTER TABLE users ADD COLUMN auth_id TEXT;
CREATE INDEX IF NOT EXISTS users_auth ON users(auth_id);
-- 보안 이벤트 기록 (로그인·기기 연결·로그아웃·삭제 — IP는 저장하지 않음, 1년 보관)
CREATE TABLE IF NOT EXISTS auth_log (id INTEGER PRIMARY KEY AUTOINCREMENT, auth_id TEXT, ev TEXT NOT NULL, ua TEXT, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS auth_log_user ON auth_log(auth_id, at);
