"""실행: python -m hub <명령>

  python -m hub run universe            종목 목록 (가장 먼저)
  python -m hub run prices [--full]     가격·배당·분할
  python -m hub run sec_filings         SEC 제출 목록
  python -m hub run sec_insider [--days 90]
  python -m hub run sec_financials [--full]
  python -m hub run short_volume [--days N]
  python -m hub run profile             개요·공매도 잔고 (주 1회)
  python -m hub run phase1              위 전부를 순서대로
  python -m hub run etf                 ETF 구성 종목·섹터 비중 (2차)
  python -m hub run options             옵션 내재변동성·풋콜 (2차)
  python -m hub run kr_etf              국내 상장 미국 ETF (2차, pykrx 필요)
  python -m hub run phase2              2차 전부
  python -m hub run news                뉴스 제목·보도자료 (3차)
  python -m hub run f13                 13F 유명 투자자·대형 운용사 보유 (3차, 분기)
  python -m hub run phase3              3차 전부 (news, f13)
  python -m hub run tenk [--full]       10-K 변화 (PC 전용, 주 1회 수동)
  python -m hub status                  마지막 실행 점검표
  python -m hub sync push|pull|ls [--dry]  Cloudflare R2 동기화
  python -m hub run daily | weekly      Actions 일정용 묶음
  python -m hub notify daily|weekly     실패·주의 시 텔레그램 알림

공통 옵션: --limit N  (소량 시험: 종목 N개 / Form 4 N건 / 공매도 N일)
"""
import argparse, sys, traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from . import core

ORDER = ["universe", "prices", "sec_filings", "sec_insider", "sec_financials", "short_volume", "profile"]
ORDER2 = ["etf", "options", "kr_etf"]
ORDER3 = ["news", "f13"]
# Actions 일정용 묶음
DAILY = ["universe", "prices", "sec_filings", "sec_insider", "sec_financials", "short_volume", "etf", "options", "kr_etf", "news"]
WEEKLY = ["profile", "f13"]


def job(name):
    from . import universe, prices, sec, short, profile, etf, options, kr_etf, news, f13, tenk
    return {"news": news.run, "f13": f13.run, "tenk": tenk.run, "etf": etf.run, "options": options.run, "kr_etf": kr_etf.run, "universe": universe.run, "prices": prices.run, "sec_filings": sec.run_filings,
            "sec_insider": sec.run_insider, "sec_financials": sec.run_financials,
            "short_volume": short.run, "profile": profile.run}[name]


def main():
    ap = argparse.ArgumentParser(prog="python -m hub", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("source", choices=ORDER + ORDER2 + ORDER3 + ["tenk", "phase1", "phase2", "phase3", "daily", "weekly"])
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--full", action="store_true")
    r.add_argument("--days", type=int, default=None)
    sub.add_parser("status")
    nt = sub.add_parser("notify")
    nt.add_argument("set", choices=["daily", "weekly"])
    nt.add_argument("--always", action="store_true")
    sy = sub.add_parser("sync")
    sy.add_argument("action", choices=["push", "pull", "ls"])
    sy.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if a.cmd == "sync":
        from . import sync
        {"push": lambda: sync.push(a.dry), "pull": lambda: sync.pull(a.dry), "ls": sync.ls}[a.action]()
        return
    if a.cmd == "notify":
        from . import notify
        names = DAILY if a.set == "daily" else WEEKLY
        sys.exit(1 if notify.run(names, f"종목 허브 {'매일' if a.set == 'daily' else '주간'} 수집", a.always) else 0)
    if a.cmd == "status":
        core.print_report(core.load_status())
        return
    names = {"phase1": ORDER, "phase2": ORDER2, "phase3": ORDER3, "daily": DAILY, "weekly": WEEKLY}.get(a.source, [a.source])
    failed = []
    for n in names:
        core.log(f"▶ {n} 시작")
        kw = {"limit": a.limit, "full": a.full}
        if a.days is not None:
            kw["days"] = a.days
        try:
            rec = job(n)(**kw)
            if rec and not rec.get("ok"):
                failed.append(n)
        except SystemExit:
            raise
        except Exception:
            traceback.print_exc()
            failed.append(n)
            if n == "universe":
                break
    if len(names) > 1:
        core.print_report([s for s in core.load_status() if s["source"] in set(names)])
    if failed:
        print("확인 필요:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
