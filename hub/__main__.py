"""실행: python -m hub <명령>

  python -m hub run universe            종목 목록 (가장 먼저)
  python -m hub run prices [--full]     가격·배당·분할
  python -m hub run sec_filings         SEC 제출 목록
  python -m hub run sec_insider [--days 90]
  python -m hub run sec_financials [--full]
  python -m hub run short_volume [--days N]
  python -m hub run profile             개요·공매도 잔고 (주 1회)
  python -m hub run phase1              위 전부를 순서대로
  python -m hub status                  마지막 실행 점검표

공통 옵션: --limit N  (소량 시험: 종목 N개 / Form 4 N건 / 공매도 N일)
"""
import argparse, sys, traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from . import core

ORDER = ["universe", "prices", "sec_filings", "sec_insider", "sec_financials", "short_volume", "profile"]


def job(name):
    from . import universe, prices, sec, short, profile
    return {"universe": universe.run, "prices": prices.run, "sec_filings": sec.run_filings,
            "sec_insider": sec.run_insider, "sec_financials": sec.run_financials,
            "short_volume": short.run, "profile": profile.run}[name]


def main():
    ap = argparse.ArgumentParser(prog="python -m hub", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("source", choices=ORDER + ["phase1"])
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--full", action="store_true")
    r.add_argument("--days", type=int, default=None)
    sub.add_parser("status")
    a = ap.parse_args()

    if a.cmd == "status":
        core.print_report(core.load_status())
        return
    names = ORDER if a.source == "phase1" else [a.source]
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
        core.print_report([s for s in core.load_status() if s["source"] in {"universe", "prices", "sec_filings", "sec_insider", "sec_financials", "short_volume", "profile"}])
    if failed:
        print("확인 필요:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
