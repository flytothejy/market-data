"""실행 결과 텔레그램 알림 — 실패·주의가 있을 때만 (환경변수 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
  python -m hub notify --names universe,prices,...   해당 수집기들의 마지막 점검표로 판단
"""
import html, os, datetime as dt
import requests

from .core import load_status, now_utc


def run(names, title="수집 점검", always=False):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    recs = {r["source"]: r for r in load_status()}
    lines, bad = [], 0
    cutoff = now_utc() - dt.timedelta(hours=6)
    for n in names:
        r = recs.get(n)
        if r is None or dt.datetime.fromisoformat(r["finished_utc"]) < cutoff:
            lines.append(f"❌ {n}: 이번 실행 기록 없음 (중간에 멈춤)"); bad += 1; continue
        if not r.get("ok"):
            lines.append(f"❌ {n}: " + html.escape("; ".join(r.get("warnings", [])[:2])[:200])); bad += 1
        elif r.get("n_warnings"):
            lines.append(f"⚠️ {n}: " + html.escape(r["warnings"][0][:150]))
        else:
            lines.append(f"✅ {n} ({r.get('seconds', 0):.0f}초)")
    warn = sum(1 for l in lines if l.startswith("⚠️"))
    print("\n".join(lines))
    if not (tok and chat) or (not bad and not warn and not always):
        return bad
    head = f"<b>{html.escape(title)}</b> — 실패 {bad} · 주의 {warn}"
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  json={"chat_id": chat, "text": head + "\n" + "\n".join(lines), "parse_mode": "HTML"}, timeout=20)
    return bad
