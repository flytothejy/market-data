"""과제 1-01: 실적 발표 이력 수집 (yfinance get_earnings_dates).

입력: 티커맵 공개 universe.json 의 개별 주식(k == 'stock')
출력: research/data/universe.csv, research/data/earnings_raw.csv
  - 종목, 발표 시각(뉴욕 현지), 예상 EPS, 실제 EPS, 서프라이즈(%)
주의: 현재 유니버스 종목만 → 생존편향. 상장폐지 종목 없음.
재실행 시 이미 받은 종목은 건너뜀 (data/raw/earn/{T}.csv 캐시).
"""
import os, sys, time
import pandas as pd, requests, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "raw", "earn")
os.makedirs(CACHE, exist_ok=True)

u = requests.get("https://tickermap.kr/api/v1/free/universe.json", timeout=60).json()
rows = pd.DataFrame(u["rows"])
uni = rows[rows["k"] == "stock"][["t", "n", "sec", "ind", "mcap", "idx"]].reset_index(drop=True)
uni.to_csv(os.path.join(DATA, "universe.csv"), index=False)
print("universe stocks:", len(uni), "asof", u.get("asof"))


def fetch(t):
    p = os.path.join(CACHE, f"{t}.csv")
    if os.path.exists(p):
        return
    ysym = t.replace(".", "-")
    for attempt in range(3):
        try:
            df = yf.Ticker(ysym).get_earnings_dates(limit=100)
            break
        except Exception as e:
            if attempt == 2:
                print("FAIL", t, e, file=sys.stderr)
                pd.DataFrame().to_csv(p + ".fail")
                return
            time.sleep(3 * (attempt + 1))
    if df is None or df.empty:
        open(p, "w").write("")
        return
    df = df.reset_index()
    df.columns = ["dt", "eps_est", "eps_act", "surp_pct"]
    # 뉴욕 현지 시각 문자열로 저장 (장전/장후 판정용)
    df["dt"] = pd.to_datetime(df["dt"]).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M")
    df.insert(0, "t", t)
    df.to_csv(p, index=False)


for i, t in enumerate(uni["t"]):
    fetch(t)
    if i % 100 == 0:
        print(i, t, flush=True)
    time.sleep(0.3)

parts = []
for t in uni["t"]:
    p = os.path.join(CACHE, f"{t}.csv")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        parts.append(pd.read_csv(p))
er = pd.concat(parts, ignore_index=True)
er.to_csv(os.path.join(DATA, "earnings_raw.csv"), index=False)
print("rows", len(er), "tickers", er["t"].nunique())
