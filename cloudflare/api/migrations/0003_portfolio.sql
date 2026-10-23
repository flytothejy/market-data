-- 포트폴리오 (로그인한 계정만 서버에 저장 · 문서 통째로, 최근 수정이 이김)
CREATE TABLE IF NOT EXISTS portfolio (uid TEXT PRIMARY KEY, data TEXT NOT NULL, u INTEGER NOT NULL);
