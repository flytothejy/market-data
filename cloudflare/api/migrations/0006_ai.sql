-- AI 문장 검색: 요청 기록(하루 횟수·자주 나오는 미지원 조건 파악용, 사람은 계정 id 또는 하루 단위 IP 해시) + 같은 문장 결과 저장
CREATE TABLE IF NOT EXISTS ai_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, day TEXT NOT NULL, who TEXT NOT NULL, q TEXT NOT NULL,
  res TEXT, n INTEGER, unsup TEXT, refused INTEGER DEFAULT 0, ms INTEGER, cached INTEGER DEFAULT 0, tok_in INTEGER, tok_out INTEGER);
CREATE INDEX IF NOT EXISTS ai_log_day_who ON ai_log (day, who);
CREATE TABLE IF NOT EXISTS ai_cache (qh TEXT PRIMARY KEY, res TEXT NOT NULL, ts INTEGER NOT NULL);
