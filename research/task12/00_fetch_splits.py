"""과제 2-7-00: EODHD 분할 이력 — 과제 1-5 R 패널 종목 전체."""
import os, json, time, requests, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = os.environ["EODHD_API_KEY"]; S = requests.Session(); rows = []
for t in pd.read_csv(os.path.join(ROOT, "data", "task5_panel_R.csv"), usecols=["t"])["t"].unique():
    code = t[2:] if t.startswith("D:") else t
    for k in range(3):
        try: r = S.get(f"https://eodhd.com/api/splits/{code}.US", params={"api_token": KEY, "fmt": "json"}, timeout=60); break
        except Exception: time.sleep(5)
    else: continue
    if r.status_code == 200:
        for x in r.json():
            a, b = x["split"].split("/"); rows.append({"t": t, "date": x["date"], "ratio": float(a) / float(b)})
    time.sleep(0.05)
D = pd.DataFrame(rows); D.to_csv(os.path.join(ROOT, "data", "raw", "eodhd", "splits_R.csv"), index=False)
print("splits", len(D), "tickers", D["t"].nunique(), "forward>=1.5:", int((D["ratio"] >= 1.5).sum()))
