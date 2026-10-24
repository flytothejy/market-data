"""생존편향 4: 상장폐지 대·중형주 → SEC CIK 연결, SEC 재무(companyfacts)·업종(SIC) 수집.

대상: _index.csv 중 어느 해든 하루 평균 거래대금 ≥ $20M, 마지막 거래일 ≥ 2011-01-01.
연결: EODHD 회사명 정규화 = SEC 회사명(과거 이름 포함) 정규화, 후보가 하나일 때만.
      CIK가 현재 유니버스 회사의 CIK와 같으면 '같은 회사(티커 변경)'로 제외.
출력: research/data/raw/sb/delisted_cik.csv, research/data/raw/r2/sec__facts_delisted.parquet (R2 facts와 같은 열)
"""
import os, re, json, time
import pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "data", "raw", "sb"); R2 = os.path.join(ROOT, "data", "raw", "r2")
CF = os.path.join(SB, "companyfacts"); os.makedirs(CF, exist_ok=True)
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}
SUFFIX = r"\b(THE|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|COS|LTD|LIMITED|PLC|HOLDINGS?|GROUP|LP|LLC|NV|SA|AG|TRUST|NEW|DEL|DE)\b"
def norm(s):
    s = str(s).upper().replace("&", " AND ")
    s = re.sub(r"\(.*?\)|/[A-Z]{2}/?$", " ", s); s = re.sub(r"[^A-Z0-9 ]", " ", s); s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()

ix = pd.read_csv(os.path.join(ROOT, "data", "prices_delisted", "_index.csv"), parse_dates=["first", "last"])
cand = ix[(ix["max_avg_dollar_vol"] >= 20e6) & (ix["last"] >= "2011-01-01")].copy()
look = {}
with open(os.path.join(SB, "cik-lookup-data.txt"), encoding="latin-1") as f:
    for line in f:
        p = line.rstrip("\n").rsplit(":", 2)
        if len(p) == 3:
            look.setdefault(norm(p[0]), set()).add(int(p[1]))
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
t2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"]))
uni_cik = {t2cik.get(t.replace(".", "-")) for t in uni["t"]} - {None}
cur_cik = set(cur["cik_str"])

out = []
for r in cand.itertuples():
    c = look.get(norm(r.name), set())
    cik = next(iter(c)) if len(c) == 1 else None
    status = "unique" if cik else ("multi" if c else "none")
    if cik and cik in uni_cik: status = "same_as_universe"
    elif cik and cik in cur_cik: status = "still_filing_other_ticker"
    out.append({"code": r.code, "name": r.name, "last": r.last.date(), "cik": cik, "status": status, "max_dv": r.max_avg_dollar_vol})
m = pd.DataFrame(out); m.to_csv(os.path.join(SB, "delisted_cik.csv"), index=False)
print(m["status"].value_counts().to_string())

# SEC 재무·SIC (상장폐지 확정 + 다른 티커로 아직 제출 중인 회사 = 우리 유니버스 밖)
use = m[m["status"].isin(["unique", "still_filing_other_ticker"])]
TAGS = None
rows, sic = [], {}
S = requests.Session(); S.headers.update(H)
for i, cik in enumerate(sorted(set(use["cik"].astype(int)))):
    p = os.path.join(CF, f"{cik}.json"); ps = os.path.join(CF, f"{cik}_sub.json")
    for url, path in ((f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", p),
                      (f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ps)):
        if os.path.exists(path): continue
        for a in range(3):
            r = S.get(url, timeout=60)
            if r.status_code == 200: open(path, "w").write(r.text); break
            if r.status_code == 404: open(path, "w").write("{}"); break
            time.sleep(2 + 3 * a)
        time.sleep(0.12)
    try:
        sj = json.load(open(ps)); sic[cik] = sj.get("sic")
        j = json.load(open(p))
    except Exception:
        continue
    for tax in ("us-gaap", "dei"):
        for tag, v in (j.get("facts", {}).get(tax, {}) or {}).items():
            for unit, arr in v.get("units", {}).items():
                for x in arr:
                    rows.append((cik, tax, tag, unit, x.get("start"), x.get("end"), x.get("val"), x.get("fy"), x.get("fp"),
                                 x.get("form"), x.get("filed"), x.get("accn"), x.get("frame")))
    if i % 200 == 0: print(i, flush=True)
fx = pd.DataFrame(rows, columns=["cik", "taxonomy", "tag", "unit", "start", "end", "val", "fy", "fp", "form", "filed", "accn", "frame"])
keep = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "GrossProfit", "CostOfRevenue",
        "CostOfGoodsAndServicesSold", "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment", "Assets", "AssetsCurrent", "LiabilitiesCurrent", "LongTermDebt",
        "LongTermDebtNoncurrent", "CashAndCashEquivalentsAtCarryingValue", "EntityCommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding"]
fx = fx[fx["tag"].isin(keep)]
fx.to_parquet(os.path.join(R2, "sec__facts_delisted.parquet"))
pd.Series(sic, name="sic").rename_axis("cik").to_csv(os.path.join(SB, "delisted_sic.csv"))
print("facts rows", len(fx), "ciks with facts", fx["cik"].nunique())
