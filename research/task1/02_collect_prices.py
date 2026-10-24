"""과제 1-02: 일봉 수집 (yfinance, 수정주가 + 시가). 2003~현재.

출력: research/data/prices/{T}.parquet (Date, Open, Close(수정), RawClose, Volume)
SPY 포함 (시장 기준선).
"""
import os, time
import pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "prices")
os.makedirs(OUT, exist_ok=True)
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
tick = ["SPY"] + list(uni["t"])
todo = [t for t in tick if not os.path.exists(os.path.join(OUT, f"{t}.parquet"))]
print("todo", len(todo))

B = 50
for i in range(0, len(todo), B):
    batch = todo[i:i + B]
    ymap = {t.replace(".", "-"): t for t in batch}
    for attempt in range(3):
        try:
            df = yf.download(list(ymap), start="2003-01-01", auto_adjust=False, actions=False,
                             group_by="ticker", progress=False, threads=True)
            break
        except Exception as e:
            print("retry", e); time.sleep(10)
    for ys, t in ymap.items():
        try:
            d = df[ys].dropna(subset=["Close"])
        except KeyError:
            continue
        if d.empty:
            continue
        # 수정 비율로 시가도 수정
        f = d["Adj Close"] / d["Close"]
        o = pd.DataFrame({"Open": d["Open"] * f, "Close": d["Adj Close"],
                          "RawClose": d["Close"], "Volume": d["Volume"]})
        o.index.name = "Date"
        o.to_parquet(os.path.join(OUT, f"{t}.parquet"))
    print(i + len(batch), flush=True)
    time.sleep(2)
print("done", len(os.listdir(OUT)))
