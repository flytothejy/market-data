-- 관리자 화면: 관리자가 한 조회·조치 기록 (누가·무엇을·언제 — 2년 보관)
CREATE TABLE IF NOT EXISTS admin_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, admin TEXT NOT NULL, action TEXT NOT NULL, target TEXT, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS admin_audit_at ON admin_audit(at);
-- 알림 발송 기록 (결과·종류·첫 줄만 — 90일 보관)
CREATE TABLE IF NOT EXISTS alert_log (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, kind TEXT, ok INTEGER NOT NULL, why TEXT, head TEXT, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS alert_log_at ON alert_log(at);
