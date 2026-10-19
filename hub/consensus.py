"""애널리스트 컨센서스 — 허브 전체 종목, 매일 쌓아서 이력으로 (yfinance)

저장: data/hub/consensus/daily/YYYY-MM.parquet  (긴 형식)
  date, ticker, block, period, field, value
  block: rev(매출 전망) · eps(EPS 전망) · eps_trend(7/30/60/90일 전 전망치) · eps_rev(30일 상향·하향 수)
         growth(성장률 전망) · pt(목표주가) · rec(투자의견 분포) · ehist(최근 4분기 예상 vs 실제)
하루 한 번 찍어 두는 스냅숏이라, 지나간 날은 다시 받을 수 없음 → 빠지지 않는 게 가장 중요
예전 S&P 500 수집분(저장소 consensus/*.csv.gz)은 처음 실행 때 함께 옮겨 담음
"""
import datetime as dt, time
import pandas as pd
import yfinance as yf

from .core import DATA, ROOT, Run, log, upsert, read
from . import universe

C_DIR = DATA / "consensus" / "daily"
KEYS = ["date", "ticker", "block", "period", "field"]
BLOCKS = (("rev", "revenue_estimate"), ("eps", "earnings_estimate"), ("eps_trend", "eps_trend"), ("eps_rev", "eps_revisions"),
          ("growth", "growth_estimates"), ("rec", "recommendations_summary"), ("ehist", "earnings_history"))


class RateLimited(Exception):
    pass


def _rate(e):
    s = str(e)
    return "Too Many Requests" in s or "Rate limit" in s or "429" in s


def _frame_rows(df, block):
    out = []
    if df is None or not hasattr(df, "iterrows") or df.empty:
        return out
    for per, r in df.iterrows():
        p = str(per.date() if hasattr(per, "date") else per)
        for f, v in r.items():
            if isinstance(v, (int, float)) and v == v:
                out.append((block, p, str(f), float(v)))
    return out


def one(tk):
    t = yf.Ticker(tk)
    rows = []
    for block, attr in BLOCKS:
        try:
            df = getattr(t, attr)
            if block == "rec" and df is not None and not df.empty and "period" in df:
                df = df.set_index("period")
            rows += _frame_rows(df, block)
        except Exception as e:
            if _rate(e):
                raise RateLimited(str(e)[:80])
    try:
        pt = t.analyst_price_targets or {}
        rows += [("pt", "now", k, float(v)) for k, v in pt.items() if isinstance(v, (int, float)) and v == v]
    except Exception as e:
        if _rate(e):
            raise RateLimited(str(e)[:80])
    return rows


def save(df):
    if df.empty:
        return
    df = df.astype({"value": "float32"})
    for m, g in df.groupby(df.date.str[:7]):
        upsert(C_DIR / f"{m}.parquet", g, KEYS)


def import_repo():
    """저장소의 S&P 500 수집분(csv.gz)을 한 번만 옮겨 담음"""
    n = 0
    for f in sorted((ROOT / "consensus").glob("*/*.csv.gz")):
        day = f.name[:10]
        cur = read(C_DIR / f"{day[:7]}.parquet", columns=["date"])
        if not cur.empty and (cur.date == day).any():
            continue
        d = pd.read_csv(f, dtype={"period": str, "field": str})
        d["ticker"] = d.ticker.str.replace(".", "-", regex=False)
        save(d[["date", "ticker", "block", "period", "field", "value"]])
        n += 1
    return n


def load(days=400):
    """최근 days일의 이력 (화면용 데이터 만들 때 사용)"""
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    files = [p for p in sorted(C_DIR.glob("*.parquet")) if p.stem >= since[:7]]
    if not files:
        return pd.DataFrame(columns=KEYS + ["value"])
    d = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    return d[d.date >= since]


def run(limit=0, **_):
    R = Run("consensus")
    imported = import_repo()
    S = universe.load("stock")
    tickers = list(S.sort_values("r1000_weight", ascending=False).ticker) if "r1000_weight" in S else list(S.ticker)
    if limit:
        tickers = tickers[:limit]
    from zoneinfo import ZoneInfo                      # 미국 동부 날짜 = 그날 장 마감 기준 스냅숏 (자정 넘겨도 같은 날짜)
    today = dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    log(f"컨센서스 수집: {len(tickers)}종목")
    rows, empty, failed, t0, n429, pause = [], [], [], time.time(), 0, 0.35
    for i, tk in enumerate(tickers, 1):
        for k in range(4):
            try:
                rs = one(tk)
                rows += [(today, tk) + r for r in rs]
                if not rs:
                    empty.append(tk)
                break
            except RateLimited as e:
                n429 += 1
                pause = min(pause * 1.5, 2.0)                # 속도 제한에 걸리면 이후 간격을 늘림
                log(f"  {tk} 속도 제한 → {60 * (k + 1)}초 쉼 ({e})")
                time.sleep(60 * (k + 1))
            except Exception as e:
                log(f"  {tk} 오류: {str(e)[:80]}")
                time.sleep(3)
        else:
            failed.append(tk)
        time.sleep(pause)
        if i % 100 == 0:
            log(f"  {i}/{len(tickers)} · 행 {len(rows):,} · {time.time()-t0:.0f}초")
            save(pd.DataFrame(rows, columns=KEYS + ["value"]))  # 중간 저장 (도중에 끊겨도 받은 만큼은 남게)
    D = pd.DataFrame(rows, columns=KEYS + ["value"])
    save(D)

    got = D.ticker.nunique() if not D.empty else 0
    with_rev = D[(D.block == "eps_rev")].ticker.nunique() if not D.empty else 0
    with_pt = D[(D.block == "pt")].ticker.nunique() if not D.empty else 0
    if failed:
        R.warning(f"받지 못한 종목 {len(failed)}개: {', '.join(failed[:20])}")
    if got < 0.8 * len(tickers):
        R.warning(f"치명: 컨센서스가 {got}/{len(tickers)}종목만 수집됨 (속도 제한 {n429}회)")
    hist = sorted({p.stem for p in C_DIR.glob('*.parquet')})
    days = load(400).date.nunique()
    R.set(tickers=len(tickers), got=got, coverage=f"{got/len(tickers)*100:.0f}%", eps_revisions=with_rev, price_targets=with_pt,
          no_analyst=len(empty), rate_limited=n429, rows_new=len(D), history_days=days, months=f"{hist[0]}~{hist[-1]}" if hist else "-",
          imported_repo_days=imported, seconds_fetch=round(time.time() - t0))
    return R.done(ok=got >= 0.8 * len(tickers))
