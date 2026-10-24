"""과제 5-04: 역DCF 정의 D(PLAN §7) 입력 준비.
1) 지금 유니버스 + 상장폐지 회사의 SEC companyfacts → 필요한 항목만 모은 facts 파일 (최초 공시 값은 다음 단계에서 처리)
2) FRED 10년 국채 일별, Damodaran 미국 내재 ERP(월별·연별)
"""
import os, io, json, time, glob
import pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "data", "raw", "sb"); CF = os.path.join(SB, "companyfacts"); MK = os.path.join(ROOT, "data", "raw", "mkt")
os.makedirs(CF, exist_ok=True); os.makedirs(MK, exist_ok=True)
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}
TAGS = {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "NetIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment", "Assets",
        "CashAndCashEquivalentsAtCarryingValue", "EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
        "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "LongTermDebtNoncurrent", "LongTermDebt",
        "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "OperatingLeaseLiability", "FinanceLeaseLiability",
        "MinorityInterest", "ShortTermInvestments", "MarketableSecuritiesCurrent", "InterestExpense"}

# --- 지금 유니버스 CIK ---
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
t2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"]))
ciks = sorted({t2cik[t.replace(".", "-")] for t in uni["t"] if t.replace(".", "-") in t2cik})
S = requests.Session(); S.headers.update(H)
for i, c in enumerate(ciks):
    p = os.path.join(CF, f"{c}.json")
    if os.path.exists(p): continue
    for a in range(3):
        r = S.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(c):010d}.json", timeout=60)
        if r.status_code == 200: open(p, "w").write(r.text); break
        if r.status_code == 404: open(p, "w").write("{}"); break
        time.sleep(2 + 3 * a)
    time.sleep(0.12)
    if i % 200 == 0: print("cf", i, flush=True)

# --- 모든 캐시에서 필요한 항목만 ---
rows = []
for p in glob.glob(os.path.join(CF, "*.json")):
    b = os.path.basename(p)
    if "_sub" in b: continue
    try: j = json.load(open(p))
    except Exception: continue
    cik = int(b.split(".")[0])
    for tax in ("us-gaap", "dei"):
        for tag, v in (j.get("facts", {}).get(tax, {}) or {}).items():
            if tag not in TAGS: continue
            for unit, arr in v.get("units", {}).items():
                for x in arr:
                    rows.append((cik, tag, x.get("start"), x.get("end"), x.get("val"), x.get("form"), x.get("filed")))
fx = pd.DataFrame(rows, columns=["cik", "tag", "start", "end", "val", "form", "filed"])
fx.to_parquet(os.path.join(SB, "facts_rdcf.parquet"))
print("facts", len(fx), "ciks", fx["cik"].nunique())

# --- 시장 입력 ---
r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", timeout=60)
open(os.path.join(MK, "DGS10.csv"), "w").write(r.text)
for u in ("https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx", "https://pages.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"):
    rr = requests.get(u, headers=H, timeout=60)
    open(os.path.join(MK, os.path.basename(u)), "wb").write(rr.content)
print("market files", os.listdir(MK))
