"""과제 2-3-00: EODHD 배당 이력(선언일 포함) 수집 — 과제 1-5 R 패널 종목. 결과를 보기 전 데이터 수집만."""
import os, json, time, requests, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "eodhd", "div"); os.makedirs(OUT, exist_ok=True)
KEY = os.environ["EODHD_API_KEY"]; S = requests.Session()
tick = pd.read_csv(os.path.join(ROOT, "data", "task5_panel_R.csv"), usecols=["t"])["t"].unique()
bad = 0
for t in tick:
    code = t[2:] if t.startswith("D:") else t
    f = os.path.join(OUT, t.replace(":", "_").replace("/", "_") + ".json")
    if os.path.exists(f): continue
    for k in range(3):
        try:
            r = S.get(f"https://eodhd.com/api/div/{code}.US", params={"api_token": KEY, "fmt": "json", "from": "2005-01-01"}, timeout=60); break
        except Exception: time.sleep(5)
    else: bad += 1; continue
    open(f, "w").write(r.text if r.status_code == 200 else "[]")
    if r.status_code != 200: bad += 1
    time.sleep(0.05)
print("done", len(tick), "failed", bad)
