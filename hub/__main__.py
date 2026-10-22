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
  python -m hub run tenk [--full]       10-K 변화 (새 10-K만, daily 묶음에 포함)
  python -m hub run insider_hist        내부자 거래 과거분 (SEC 분기 데이터, 2010~, 주간 묶음)
  python -m hub run cards               주간 홍보 카드 (SNS용 이미지, 주간 묶음에 포함)
  python -m hub run check               이상값 점검 (build 다음에 자동)
  python -m hub run build               화면용 JSON 만들기 (site/api/v1, daily·weekly 끝에 자동 실행)
  python -m hub status                  마지막 실행 점검표
  python -m hub sync push|pull|ls [--dry]  Cloudflare R2 동기화
  python -m hub run daily | weekly      Actions 일정용 묶음
  python -m hub run close               마감 직후 빠른 갱신 (종가·옵션·화면)
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
ORDER3 = ["news", "f13", "consensus"]
# Actions 일정용 묶음
DAILY = ["universe", "prices", "sec_filings", "sec_insider", "sec_financials", "short_volume", "etf", "options", "kr_etf", "news", "consensus", "tenk", "build", "check", "alerts"]
WEEKLY = ["profile", "f13", "insider_hist", "build", "check", "cards"]
# 미국장 마감 직후(동부 16:20) 빠른 갱신: 종가·옵션만 받고 화면 데이터 재생성 (~10분). 나머지는 저녁 daily가 채움
CLOSE = ["universe", "prices", "options", "build", "check"]


def job(name):
    from . import universe, prices, sec, short, profile, etf, options, kr_etf, news, f13, tenk, build, consensus, check, cards, insider_hist, alerts
    return {"alerts": alerts.run, "insider_hist": insider_hist.run, "cards": cards.run, "check": check.run, "consensus": consensus.run, "build": build.run, "news": news.run, "f13": f13.run, "tenk": tenk.run, "etf": etf.run, "options": options.run, "kr_etf": kr_etf.run, "universe": universe.run, "prices": prices.run, "sec_filings": sec.run_filings,
            "sec_insider": sec.run_insider, "sec_financials": sec.run_financials,
            "short_volume": short.run, "profile": profile.run}[name]


def _record_fail(name, msg):
    """예외로 끝난 수집기도 점검 기록을 남김 (알림·Actions 주석에 원인이 보이게)"""
    import os
    r = core.Run(name)
    r.warning("치명: " + str(msg)[:500])
    r.done(ok=False)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title={name}::" + str(msg).replace("\n", " ")[:900])


def main():
    ap = argparse.ArgumentParser(prog="python -m hub", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("source", help="수집기 이름, 묶음(daily·weekly·phase1~3), 또는 쉼표로 여러 개 (예: prices,build)")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--full", action="store_true")
    r.add_argument("--days", type=int, default=None)
    sub.add_parser("status")
    nt = sub.add_parser("notify")
    nt.add_argument("set", help="daily · weekly · 또는 수집기 이름")
    nt.add_argument("--always", action="store_true")
    sy = sub.add_parser("sync")
    sy.add_argument("action", choices=["push", "pull", "ls"])
    sy.add_argument("--only", nargs="*", help="이 경로로 시작하는 파일만 (예: ref/ — PC에서는 꼭 지정)")
    sy.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if a.cmd == "sync":
        from . import sync
        {"push": lambda: sync.push(a.dry, a.only), "pull": lambda: sync.pull(a.dry, a.only), "ls": sync.ls}[a.action]()
        return
    if a.cmd == "notify":
        from . import notify
        names = {"daily": DAILY, "weekly": WEEKLY, "close": CLOSE}.get(a.set, [x.strip() for x in a.set.split(",")])
        title = {"daily": "매일", "weekly": "주간", "close": "마감 직후"}.get(a.set, a.set)
        sys.exit(1 if notify.run(names, f"종목 허브 {title} 수집", a.always) else 0)
    if a.cmd == "status":
        core.print_report(core.load_status())
        return
    groups = {"phase1": ORDER, "phase2": ORDER2, "phase3": ORDER3, "daily": DAILY, "weekly": WEEKLY, "close": CLOSE}
    names = [n for part in a.source.split(",") for n in groups.get(part.strip(), [part.strip()])]
    valid = set(ORDER + ORDER2 + ORDER3 + ["tenk", "build", "check", "cards", "insider_hist", "alerts"])
    bad = [n for n in names if n not in valid]
    if bad:
        sys.exit(f"모르는 수집기: {', '.join(bad)} (가능: {', '.join(sorted(valid))})")
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
        except SystemExit as e:                     # 설정 누락 등 — 나머지 수집기는 계속
            msg = str(e.code if e.code is not None else "")
            print(msg)
            _record_fail(n, msg)
            failed.append(n)
            if n == "universe" and not (core.DATA / "universe" / "universe.parquet").exists():
                break                               # 이전 종목 목록이 있으면 그걸로 나머지 계속
        except Exception as e:
            traceback.print_exc()
            _record_fail(n, f"{type(e).__name__}: {e}")
            failed.append(n)
            if n == "universe" and not (core.DATA / "universe" / "universe.parquet").exists():
                break
    if len(names) > 1:
        core.print_report([s for s in core.load_status() if s["source"] in set(names)])
    if failed:
        print("확인 필요:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
