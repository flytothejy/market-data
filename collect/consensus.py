#!/usr/bin/env python3
"""
애널리스트 컨센서스 일별 수집 (yfinance) → consensus/YYYY/YYYY-MM-DD.csv.gz
  대상: sp500_tickers.txt
  블록: rev(매출 전망) · eps(EPS 전망) · eps_trend(전망치 변화 7/30/60/90일 전) · eps_rev(상향·하향 수)
        growth(성장률 전망) · pt(목표주가) · rec(투자의견 분포) · ehist(최근 4분기 예상 vs 실제 EPS)
  형식(긴 형식): date, ticker, block, period, field, value
사용: python collect/consensus.py [--limit N]
"""
import argparse, datetime, gzip, os, sys, time
import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame_rows(df, block):
    out = []
    if df is None or not hasattr(df, "iterrows") or df.empty:
        return out
    for per, r in df.iterrows():
        for f, v in r.items():
            if v is None or (isinstance(v, float) and v != v):
                continue
            if isinstance(v, (int, float)):
                out.append((block, str(per.date() if hasattr(per, "date") else per), str(f), float(v)))
    return out


def one(tk):
    t = yf.Ticker(tk.replace(".", "-"))
    rows = []
    for block, fn in (("rev", lambda: t.revenue_estimate), ("eps", lambda: t.earnings_estimate), ("eps_trend", lambda: t.eps_trend),
                      ("eps_rev", lambda: t.eps_revisions), ("growth", lambda: t.growth_estimates),
                      ("rec", lambda: t.recommendations_summary), ("ehist", lambda: t.earnings_history)):
        try:
            df = fn()
            if block == "rec" and df is not None and not df.empty and "period" in df:
                df = df.set_index("period")
            rows += frame_rows(df, block)
        except Exception as e:
            if "Too Many Requests" in str(e) or "Rate" in str(e):
                raise
    try:
        pt = t.analyst_price_targets or {}
        rows += [("pt", "now", k, float(v)) for k, v in pt.items() if isinstance(v, (int, float))]
    except Exception as e:
        if "Too Many Requests" in str(e) or "Rate" in str(e):
            raise
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    tickers = [x.strip() for x in open(os.path.join(ROOT, "sp500_tickers.txt")) if x.strip()]
    if a.limit:
        tickers = tickers[:a.limit]
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    allrows, fail, t0 = [], [], time.time()
    for i, tk in enumerate(tickers, 1):
        for k in range(3):
            try:
                rows = one(tk)
                allrows += [(today, tk) + r for r in rows]
                if not rows:
                    fail.append(tk)
                break
            except Exception as e:
                print(tk, "재시도", k, str(e)[:80], flush=True)
                time.sleep(30 * (k + 1))
        else:
            fail.append(tk)
        time.sleep(0.4)
        if i % 50 == 0:
            print(f"  {i}/{len(tickers)}  행 {len(allrows):,}  {time.time()-t0:.0f}초", flush=True)
    df = pd.DataFrame(allrows, columns=["date", "ticker", "block", "period", "field", "value"])
    d = os.path.join(ROOT, "consensus", today[:4]); os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"{today}.csv.gz")
    with gzip.open(fp, "wt", encoding="utf-8") as f:
        df.to_csv(f, index=False)
    got = df.ticker.nunique()
    print(f"완료: {got}/{len(tickers)}종목, {len(df):,}행 → {fp} ({time.time()-t0:.0f}초), 빈 결과 {len(fail)}개: {' '.join(fail[:30])}")
    if got < 0.5 * len(tickers):
        print(f"::error title=컨센서스 수집 부족::{got}/{len(tickers)}종목만 수집")
        sys.exit(1)


if __name__ == "__main__":
    main()
