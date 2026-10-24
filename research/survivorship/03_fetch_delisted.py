"""생존편향 3: EODHD 상장폐지 미국 보통주 전체의 일별 가격 수집 (2003~).

출력: research/data/prices_delisted/{CODE}.parquet (Date, Close=수정종가, RawClose, Volume)
      research/data/prices_delisted/_index.csv (코드, 이름, 거래소, 행 수, 첫·마지막 날짜, 최대 연간 평균 거래대금)
열쇠는 환경변수 EODHD_API_KEY(저장소 밖 파일)에서만 읽는다. 재실행 시 받은 종목은 건너뛴다.
"""
import os, io, json, time, threading
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "prices_delisted"); os.makedirs(OUT, exist_ok=True)
KEY = os.environ["EODHD_API_KEY"]
d = pd.DataFrame(json.load(open(os.path.join(ROOT, "data", "raw", "eodhd", "us_delisted.json"))))
d = d[d["Type"] == "Common Stock"].reset_index(drop=True)
lock = threading.Lock(); stats = []
S = requests.Session()

def fetch(row):
    code = row["Code"]; safe = code.replace("/", "_")
    p = os.path.join(OUT, f"{safe}.parquet"); e = p + ".empty"
    if os.path.exists(p) or os.path.exists(e):
        return
    for a in range(4):
        try:
            r = S.get(f"https://eodhd.com/api/eod/{code}.US", params={"api_token": KEY, "fmt": "csv", "from": "2003-01-01"}, timeout=60)
        except requests.RequestException:
            time.sleep(2 + 3 * a); continue
        if r.status_code == 200: break
        if r.status_code in (429, 500, 502, 503): time.sleep(5 + 10 * a); continue
        open(e, "w").write(str(r.status_code)); return
    else:
        return
    try:
        x = pd.read_csv(io.StringIO(r.text))
    except Exception:
        open(e, "w").write("parse"); return
    if x.empty or "Date" not in x.columns:
        open(e, "w").write("empty"); return
    x["Date"] = pd.to_datetime(x["Date"], errors="coerce"); x = x.dropna(subset=["Date", "Close"])
    if x.empty:
        open(e, "w").write("empty"); return
    o = pd.DataFrame({"Close": x["Adjusted_close"].values, "RawClose": x["Close"].values, "Volume": x["Volume"].values},
                     index=pd.DatetimeIndex(x["Date"], name="Date"))
    o.to_parquet(p)

with ThreadPoolExecutor(max_workers=8) as ex:
    for i, _ in enumerate(ex.map(fetch, [r for _, r in d.iterrows()])):
        if i % 1000 == 0:
            print(i, flush=True)

# 색인: 행 수, 기간, 연도별 평균 거래대금(원종가×거래량) 최대값
rows = []
for _, r in d.iterrows():
    p = os.path.join(OUT, f"{r['Code'].replace('/', '_')}.parquet")
    if not os.path.exists(p): continue
    x = pd.read_parquet(p)
    dv = (x["RawClose"] * x["Volume"]).groupby(x.index.year).mean()
    rows.append({"code": r["Code"], "name": r["Name"], "exchange": r["Exchange"], "isin": r.get("Isin"), "rows": len(x),
                 "first": x.index.min().date(), "last": x.index.max().date(), "max_avg_dollar_vol": dv.max() if len(dv) else 0})
pd.DataFrame(rows).to_csv(os.path.join(OUT, "_index.csv"), index=False)
print("files", len(rows))
