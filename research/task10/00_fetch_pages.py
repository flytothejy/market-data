"""과제 2-5-00: R 패널 회사의 SEC 제출 이력 이전 페이지(빠진 것) 받기 — 8-K 1.03(파산) 이력용."""
import os, json, time, requests, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); CF = os.path.join(ROOT, "data", "raw", "sb", "companyfacts")
S = requests.Session(); S.headers.update({"User-Agent": "tickermap-research flytothejy@gmail.com"})
pn = pd.read_csv(os.path.join(ROOT, "data", "task5_panel_R.csv"), usecols=["t"])
cur = pd.DataFrame(json.load(open(os.path.join(ROOT, "data", "raw", "sb", "company_tickers.json"))).values()); cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False)
now2cik = dict(zip(cur["ticker"], cur["cik_str"])); dm = pd.read_csv(os.path.join(ROOT, "data", "raw", "sb", "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
n = 0
for t in pn["t"].unique():
    c = d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
    if c is None or c != c: continue
    p = os.path.join(CF, f"{int(c)}_sub.json")
    if not os.path.exists(p): continue
    for fo in json.load(open(p)).get("filings", {}).get("files", []):
        fp = os.path.join(CF, f"{int(c)}_{fo['name']}")
        if os.path.exists(fp): continue
        r = S.get(f"https://data.sec.gov/submissions/{fo['name']}", timeout=60); time.sleep(0.12)
        if r.status_code == 200: open(fp, "w").write(r.text); n += 1
print("fetched", n)
