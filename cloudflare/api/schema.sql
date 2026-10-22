-- 티커맵 API (D1) — Cloudflare 대시보드 D1 → tickermap → Console에 통째로 붙여넣고 실행
-- 로그인 전 단계: 기기마다 무작위 기기코드(해시만 저장) → 사용자 하나. 나중에 로그인을 붙이면 users에 계정만 연결하면 됨

CREATE TABLE IF NOT EXISTS users (
  uid      TEXT PRIMARY KEY,
  chat_id  INTEGER,              -- 텔레그램 대화방 (연결 전이면 NULL)
  tg_name  TEXT,
  mode     TEXT DEFAULT 'digest', -- digest(아침 묶음) · off
  created  INTEGER,
  linked   INTEGER
);
CREATE INDEX IF NOT EXISTS users_chat ON users(chat_id);

CREATE TABLE IF NOT EXISTS devices (
  code_hash TEXT PRIMARY KEY,     -- 기기코드의 SHA-256 (코드 자체는 브라우저에만)
  uid       TEXT NOT NULL,
  created   INTEGER,
  seen      INTEGER
);
CREATE INDEX IF NOT EXISTS devices_uid ON devices(uid);

-- 한 번 쓰고 버리는 연결 토큰 (10분): tg = 텔레그램 연결, dev = 다른 기기 추가
CREATE TABLE IF NOT EXISTS tokens (
  token TEXT PRIMARY KEY,
  uid   TEXT NOT NULL,
  kind  TEXT NOT NULL,
  exp   INTEGER NOT NULL
);

-- 후보함: 사용자당 한 줄(JSON 배열). 항목마다 수정 시각 u — 더 최근 것이 이김. 지운 항목은 {t,u,del:1}로 남겨 다른 기기에도 지워지게
-- (한 줄로 두는 이유: 무료 요금제는 요청 한 번에 D1 쿼리 50개까지라, 항목마다 한 줄이면 큰 후보함 첫 동기화가 막힘)
CREATE TABLE IF NOT EXISTS watch (
  uid  TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  u    INTEGER NOT NULL
);
