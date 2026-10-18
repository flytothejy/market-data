#!/usr/bin/env python3
"""목업용 1회성 스냅샷: 503종목 주가 지표·기본 재무(yfinance info)·내부자 거래 → snapshot/*.csv"""
import os, sys, time
import numpy as np, pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "snapshot"); os.makedirs(OUT, exist_ok=True)
tks = [l.strip() for l in open(os.path.join(ROOT, "sp500_tickers.txt")) if l.strip()]
ytk = {t: t.replace(".", "-") for t in tks}

# 1) 가격 지표
px = yf.download(list(ytk.values()) + ["SPY"], period="2y", interval="1d", group_by="ticker",
                 auto_adjust=True, threads=True, progress=False)
rows = []
for t in tks + ["SPY"]:
    try:
        d = px[ytk.get(t, t)].dropna(subset=["Close"])
        c, v = d["Close"], d["Volume"]
        if len(c) < 260: continue
        dlt = c.diff(); up = dlt.clip(lower=0).ewm(alpha=1/14).mean(); dn = (-dlt.clip(upper=0)).ewm(alpha=1/14).mean()
        rsi = 100 - 100 / (1 + up / dn)
        s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
        cross = (s50 > s200).astype(int).diff()
        last_gc = cross[cross == 1].index.max(); last_dc = cross[cross == -1].index.max()
        hi52, lo52 = c[-252:].max(), c[-252:].min()
        rows.append(dict(ticker=t, close=c.iloc[-1], r1d=c.iloc[-1]/c.iloc[-2]-1, r1m=c.iloc[-1]/c.iloc[-22]-1,
                         r3m=c.iloc[-1]/c.iloc[-64]-1, r12m=c.iloc[-1]/c.iloc[-253]-1,
                         r12_1=c.iloc[-22]/c.iloc[-253]-1, d200=c.iloc[-1]/s200.iloc[-1]-1, d50=c.iloc[-1]/s50.iloc[-1]-1,
                         rsi14=rsi.iloc[-1], hi52=c.iloc[-1]/hi52-1, lo52=c.iloc[-1]/lo52-1,
                         vol20=v[-20:].mean()/v[-120:].mean(), volat60=c.pct_change()[-60:].std()*np.sqrt(252),
                         gc=str(last_gc.date()) if pd.notna(last_gc) else "", dc=str(last_dc.date()) if pd.notna(last_dc) else "",
                         asof=str(c.index[-1].date())))
    except Exception as e:
        print("px", t, e, file=sys.stderr)
pd.DataFrame(rows).to_csv(os.path.join(OUT, "tech.csv"), index=False)
# 월말 종가 (포트폴리오 목업용)
m = pd.DataFrame({t: px[ytk.get(t, t)]["Close"] for t in tks + ["SPY"] if ytk.get(t, t) in px.columns.get_level_values(0)})
m.resample("ME").last().round(3).to_csv(os.path.join(OUT, "monthly.csv"))
m.iloc[-260:].round(3).to_csv(os.path.join(OUT, "daily1y.csv.gz"))
print("tech", len(rows))

# 2) 기본 재무 + 3) 내부자
F = ["shortName","sector","industry","marketCap","trailingPE","forwardPE","priceToBook","pegRatio","returnOnEquity","returnOnAssets",
     "grossMargins","operatingMargins","profitMargins","revenueGrowth","earningsGrowth","debtToEquity","freeCashflow","totalRevenue",
     "dividendYield","earningsTimestamp","earningsTimestampStart","heldPercentInsiders","shortPercentOfFloat","beta"]
info, ins = [], []
for i, t in enumerate(tks):
    T = yf.Ticker(ytk[t])
    try:
        d = T.info or {}
        info.append({"ticker": t, **{k: d.get(k) for k in F}})
    except Exception as e:
        print("info", t, e, file=sys.stderr)
    try:
        it = T.insider_transactions
        if it is not None and not it.empty:
            it = it.copy(); it["ticker"] = t
            ins.append(it)
    except Exception as e:
        print("ins", t, e, file=sys.stderr)
    if i % 50 == 0: print(i, flush=True)
    time.sleep(0.2)
pd.DataFrame(info).to_csv(os.path.join(OUT, "info.csv"), index=False)
if ins:
    pd.concat(ins).to_csv(os.path.join(OUT, "insider.csv.gz"), index=False)
print("done", len(info), sum(len(x) for x in ins))
