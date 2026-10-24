"""과제 4-02: CUSIP → 티커 (티커맵 cusip 표 + OpenFIGI), 유니버스 밖 종목 가격 추가 수집."""
import os, json, time
import pandas as pd, requests, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = os.path.join(ROOT, "data", "raw", "r2"); RAW = os.path.join(ROOT, "data", "raw", "f13"); PX = os.path.join(ROOT, "data", "prices")
h = pd.read_parquet(os.path.join(RAW, "holdings_hist.parquet"))
h = h[(h["sh_type"] == "SH") & (h["put_call"].fillna("") == "")]
cus = sorted(set(h["cusip"].str.upper().str.zfill(9)))
cmap = pd.read_parquet(os.path.join(R2, "f13__cusip.parquet")).dropna(subset=["ticker"])
known = dict(zip(cmap["cusip"].str.upper(), cmap["ticker"]))
cache_p = os.path.join(RAW, "figi_cache.json")
figi = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
todo = [c for c in cus if c not in known and c not in figi]
print("cusips", len(cus), "known", sum(c in known for c in cus), "todo figi", len(todo))
for i in range(0, len(todo), 10):
    batch = todo[i:i + 10]
    for a in range(5):
        r = requests.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_CUSIP", "idValue": c} for c in batch], timeout=60)
        if r.status_code == 200: break
        time.sleep(15 * (a + 1))
    if r.status_code != 200:
        print("figi fail", r.status_code); break
    for c, res in zip(batch, r.json()):
        d = res.get("data") or []
        us = [x for x in d if x.get("exchCode") == "US" and x.get("marketSector") == "Equity"] or d
        figi[c] = us[0]["ticker"] if us else None
    if i % 200 == 0:
        json.dump(figi, open(cache_p, "w")); print(i, flush=True)
    time.sleep(2.5)                                   # 무료 한도: 분당 25회
json.dump(figi, open(cache_p, "w"))
c2t = {c: (known.get(c) or figi.get(c)) for c in cus}
pd.Series(c2t, name="ticker").rename_axis("cusip").to_csv(os.path.join(RAW, "cusip_ticker.csv"))
tick = sorted({t.replace("/", "-").replace(" ", "-").replace(".", "-") for t in c2t.values() if t})
need = [t for t in tick if not os.path.exists(os.path.join(PX, f"{t}.parquet"))]
print("mapped", sum(v is not None for v in c2t.values()), "/", len(cus), "| tickers", len(tick), "need prices", len(need))
for i in range(0, len(need), 50):
    b = need[i:i + 50]
    try:
        df = yf.download(b, start="2013-01-01", auto_adjust=False, actions=False, group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print("dl fail", e); continue
    for t in b:
        try:
            d = df[t].dropna(subset=["Close"]) if len(b) > 1 else df.dropna(subset=["Close"])
        except KeyError:
            continue
        if len(d) < 60: continue
        f = d["Adj Close"] / d["Close"]
        o = pd.DataFrame({"Open": d["Open"] * f, "Close": d["Adj Close"], "RawClose": d["Close"], "Volume": d["Volume"]}); o.index.name = "Date"
        o.to_parquet(os.path.join(PX, f"{t}.parquet"))
    print("prices", i + len(b), flush=True)
print("done; price files now", len(os.listdir(PX)))
