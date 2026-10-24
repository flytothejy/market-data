-- 사용자 설정 (로그인한 계정만 서버에 — 문서 통째로, 최근 수정이 이김. 로그인 안 하면 브라우저에만)
CREATE TABLE IF NOT EXISTS prefs (auth_id TEXT PRIMARY KEY, data TEXT NOT NULL, u INTEGER NOT NULL);
