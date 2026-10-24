"""데이터 오류 수정: yfinance 'Close'(=RawClose)는 이후 주식분할이 이미 반영된 가격이다.
시점 시가총액 = 그날의 실제 주가 × 그 시점 발행주식수 이므로, 실제 주가 RawUnadj = RawClose × (그날 이후 분할 비율의 곱)을 만든다.
분할 이력: yfinance Ticker.splits (티커맵 유니버스 + 과제 3·5에서 쓰는 가격 파일).
EODHD 상장폐지 가격(prices_delisted)은 원가격이라 RawUnadj = RawClose.
"""
import os, time
import numpy as np, pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PX = os.path.join(ROOT, "data", "prices"); PXD = os.path.join(ROOT, "data", "prices_delisted")
OUT = os.path.join(ROOT, "survivorship", "out")
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
targets = sorted({t.replace(".", "-") for t in uni["t"]} | {"SPY"})
log = []
for i, t in enumerate(targets):
    p = os.path.join(PX, f"{t}.parquet")
    if not os.path.exists(p): continue
    x = pd.read_parquet(p)
    for a in range(3):
        try:
            sp = yf.Ticker(t).splits; break
        except Exception:
            time.sleep(3); sp = None
    if sp is None: log.append((t, "fail", 0)); continue
    sp = sp[sp > 0]
    if len(sp):
        sp.index = pd.to_datetime(sp.index).tz_localize(None).normalize()
    fac = pd.Series(1.0, index=x.index)
    for d, r in sp.items():
        fac[x.index < d] *= r                       # 분할일 이전 가격은 r배였다
    x["RawUnadj"] = x["RawClose"] * fac.values
    x.to_parquet(p)
    log.append((t, "ok", len(sp)))
    if i % 200 == 0: print(i, flush=True)
for f in os.listdir(PXD):
    if not f.endswith(".parquet"): continue
    p = os.path.join(PXD, f); x = pd.read_parquet(p)
    if "RawUnadj" not in x.columns:
        x["RawUnadj"] = x["RawClose"]; x.to_parquet(p)
pd.DataFrame(log, columns=["t", "status", "n_splits"]).to_csv(os.path.join(OUT, "split_fix_log.csv"), index=False)
lg = pd.DataFrame(log, columns=["t", "status", "n_splits"])
print("done", lg["status"].value_counts().to_dict(), "tickers with splits", int((lg["n_splits"] > 0).sum()))
nf = pd.read_parquet(os.path.join(PX, "NFLX.parquet"))
print("NFLX 2025-09-30 RawClose / RawUnadj:", round(nf.loc[:"2025-09-30", "RawClose"].iloc[-1], 2), round(nf.loc[:"2025-09-30", "RawUnadj"].iloc[-1], 2))
