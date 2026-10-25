"""과제 2-6-00: 행동주의 펀드(제출자) SEC 제출 이력 받기 → 원본 13D 공시 번호 목록."""
import os, json, time, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "sb", "activist_subs"); os.makedirs(OUT, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "tickermap-research flytothejy@gmail.com"})
A = json.load(open(os.path.join(ROOT, "task11", "activist_ciks.json")))
BAD = ("GOLD MINES", "POLITANO")
ciks = {}
for fund, lst in A.items():
    for c, n in lst:
        if not any(b in n for b in BAD): ciks[c] = fund
def get(url):
    for k in range(5):
        try:
            r = S.get(url, timeout=60); time.sleep(0.12)
            if r.status_code in (200, 404): return r
        except Exception: pass
        time.sleep(3 * (k + 1))
rows = []
for c, fund in ciks.items():
    f = os.path.join(OUT, f"{c}.json")
    if not os.path.exists(f):
        r = get(f"https://data.sec.gov/submissions/CIK{c:010d}.json"); open(f, "w").write(r.text if r is not None and r.status_code == 200 else "{}")
    j = json.load(open(f)); parts = [j.get("filings", {}).get("recent", {})]
    for fo in j.get("filings", {}).get("files", []):
        fp = os.path.join(OUT, f"{c}_{fo['name']}")
        if not os.path.exists(fp):
            r = get(f"https://data.sec.gov/submissions/{fo['name']}"); open(fp, "w").write(r.text if r is not None and r.status_code == 200 else "{}")
        parts.append(json.load(open(fp)))
    for pt in parts:
        for a, fm, d in zip(pt.get("accessionNumber", []), pt.get("form", []), pt.get("filingDate", [])):
            if fm in ("SC 13D", "SCHEDULE 13D"): rows.append({"acc": a, "date": d, "fund": fund, "filer_cik": c})
import pandas as pd
D = pd.DataFrame(rows).drop_duplicates("acc"); D.to_csv(os.path.join(ROOT, "task11", "activist_13d.csv"), index=False)
print("filer ciks", len(ciks), "original 13D filings", len(D)); print(D.groupby("fund").size().sort_values(ascending=False).head(15).to_dict())
