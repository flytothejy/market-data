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
    if os.environ.get("GITHUB_ACTIONS"):               # Actions 화면·API에서 바로 보이게 주석과 요약으로도 남김
        # 한 단계당 주석은 종류별 10개까지만 보이므로 마지막 단계(build)를 먼저
        for n in sorted(names, key=lambda x: x != "build"):
            r = recs.get(n) or {}
            w = "; ".join(r.get("warnings", [])[:3]).replace("\n", " ")[:900]
            stale = r and dt.datetime.fromisoformat(r["finished_utc"]) < cutoff
            if not r or stale or not r.get("ok"):
                print(f"::error title={n}::{'이번 실행 기록 없음 (중간에 멈춤)' if (not r or stale) else w}")
            elif r.get("n_warnings"):
                print(f"::warning title={n}::{w}")
        # 결과는 한 개의 주석에 모아서 (한 단계당 주석 10개 제한 때문에 잘리지 않게)
        summ = []
        for n in names:
            r = recs.get(n) or {}
            if r and not (dt.datetime.fromisoformat(r["finished_utc"]) < cutoff):
                keys = [k for k in r if k not in ("source", "ok", "finished_utc", "warnings", "n_warnings", "history")][:10]
                summ.append(f"[{n}] " + " · ".join(f"{k}={r[k]}" for k in keys)[:600])
        if summ:
            print("::notice title=수집 결과::" + "%0A".join(x.replace("%", "%25").replace("\n", " ") for x in summ))
        p = os.environ.get("GITHUB_STEP_SUMMARY")
        if p:
            with open(p, "a", encoding="utf-8") as f:
                f.write("### " + title + "\n\n" + "\n".join(f"- {html.unescape(l)}" for l in lines) + "\n")
    if not (tok and chat) or (not bad and not warn and not always):
        return bad
    head = f"<b>{html.escape(title)}</b> — 실패 {bad} · 주의 {warn}"
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  json={"chat_id": chat, "text": head + "\n" + "\n".join(lines), "parse_mode": "HTML"}, timeout=20)
    return bad
