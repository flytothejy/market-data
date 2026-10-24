"""과제 5-01: 리밸런싱일 × 종목 재무 신호 패널 (PLAN.md §1·§2). 모든 값은 최초 공시일 이후에만 사용."""
import os, json, bisect
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); R2 = os.path.join(DATA, "raw", "r2"); PX = os.path.join(DATA, "prices")

TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "GrossProfit", "CostOfRevenue",
        "CostOfGoodsAndServicesSold", "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment", "Assets", "AssetsCurrent", "LiabilitiesCurrent", "LongTermDebt",
        "LongTermDebtNoncurrent", "CashAndCashEquivalentsAtCarryingValue", "EntityCommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding"]
f = pd.read_parquet(os.path.join(R2, "sec__facts.parquet"), columns=["cik", "tag", "start", "end", "filed", "val"])
f = f[f["tag"].isin(TAGS)].copy()
for c in ("start", "end", "filed"):
    f[c] = pd.to_datetime(f[c])
f = f.sort_values("filed").drop_duplicates(["cik", "tag", "start", "end"], keep="first")   # 최초 공시 값만
f["dur"] = (f["end"] - f["start"]).dt.days
F = {}
for (c, t), g in f.groupby(["cik", "tag"]):
    g = g.sort_values("filed")
    F[(c, t)] = (g["filed"].values, g["start"].values, g["end"].values, g["dur"].values, g["val"].values)
print("fact series", len(F))
DAY = np.timedelta64(1, "D")

def _rows(c, t, d):
    s = F.get((c, t))
    if s is None: return None
    k = np.searchsorted(s[0], np.datetime64(d), side="left")       # filed < d
    if k == 0: return None
    return [a[:k] for a in s]

def inst(c, t, d):
    r = _rows(c, t, d)
    if r is None: return np.nan
    fl, st, en, du, va = r
    m = np.isnan(du.astype(float))
    if not m.any(): return np.nan
    en_, va_ = en[m], va[m]
    i = np.argmax(en_)
    return va_[i] if en_[i] >= np.datetime64(d) - 200 * DAY else np.nan

def ttm(c, t, d):
    r = _rows(c, t, d)
    if r is None: return np.nan
    fl, st, en, du, va = r
    du = du.astype(float); ok = du >= 80
    if not ok.any(): return np.nan
    le = en[ok].max()
    if le < np.datetime64(d) - 200 * DAY: return np.nan
    cand = ok & (en == le) & (du <= 380)
    if not cand.any(): return np.nan
    j = np.where(cand)[0][np.argmax(du[cand])]
    D = du[j]
    if 350 <= D <= 380: return va[j]
    if not (80 <= D <= 290): return np.nan
    fy_end = st[j] - DAY
    fy = np.where((du >= 350) & (du <= 380) & (np.abs((en - fy_end) / DAY) <= 10))[0]
    py = np.where((np.abs(du - D) <= 10) & (np.abs((en - (le - 365 * DAY)) / DAY) <= 10))[0]
    if len(fy) == 0 or len(py) == 0: return np.nan
    return va[fy[-1]] + va[j] - va[py[-1]]

def first_ok(*vals):
    for v in vals:
        if v == v: return v
    return np.nan

def rev(c, d): return first_ok(ttm(c, "Revenues", d), ttm(c, "RevenueFromContractWithCustomerExcludingAssessedTax", d), ttm(c, "SalesRevenueNet", d))
def gp(c, d):
    g = ttm(c, "GrossProfit", d)
    if g == g: return g
    return rev(c, d) - first_ok(ttm(c, "CostOfRevenue", d), ttm(c, "CostOfGoodsAndServicesSold", d))
def shares(c, d):
    for t in ("EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"):
        r = _rows(c, t, d)
        if r is None: continue
        fl, va = r[0], r[4]
        m = fl >= np.datetime64(d) - 200 * DAY
        if m.any(): return va[m][-1]
    return np.nan
def debt(c, d):
    return first_ok(inst(c, "LongTermDebt", d), inst(c, "LongTermDebtNoncurrent", d), 0.0)

def snap(c, d):
    A = inst(c, "Assets", d); NI = ttm(c, "NetIncomeLoss", d); CFO = ttm(c, "NetCashProvidedByUsedInOperatingActivities", d)
    CAPEX = ttm(c, "PaymentsToAcquirePropertyPlantAndEquipment", d); R = rev(c, d); G = gp(c, d)
    CA = inst(c, "AssetsCurrent", d); CL = inst(c, "LiabilitiesCurrent", d)
    return dict(A=A, NI=NI, CFO=CFO, CAPEX=CAPEX, R=R, G=G, CR=CA / CL if CL and CL == CL else np.nan,
                LEV=debt(c, d) / A if A else np.nan, SH=shares(c, d), CASH=inst(c, "CashAndCashEquivalentsAtCarryingValue", d), DEBT=debt(c, d))

def rdcf(ev, fcf, r=0.09, gt=0.025):
    if not (ev == ev and fcf == fcf) or fcf <= 0 or ev <= 0: return np.nan
    def val(g):
        pv = sum(fcf * (1 + g) ** t / (1 + r) ** t for t in range(1, 11))
        return pv + fcf * (1 + g) ** 10 * (1 + gt) / (r - gt) / (1 + r) ** 10
    lo, hi = -0.20, 0.60
    if val(lo) > ev: return lo
    if val(hi) < ev: return hi
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if val(m) < ev else (lo, m)
    return (lo + hi) / 2

# ---------- 유니버스 ----------
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False); now2cik = dict(zip(cur["ticker"], cur["cik_str"]))
uni = pd.read_csv(os.path.join(DATA, "universe.csv")); uni["t2"] = uni["t"].str.replace(".", "-", regex=False)
prof = pd.read_parquet(os.path.join(R2, "profile__profile.parquet"))[["ticker", "country"]]
us = set(prof.loc[prof["country"] == "United States", "ticker"].str.replace(".", "-", regex=False))
uni = uni[uni["t2"].isin(us) & ~uni["sec"].isin(["Financial Services", "Real Estate"])]
pool = [t for t in uni["t2"] if t in now2cik and os.path.exists(os.path.join(PX, f"{t}.parquet"))]
print("pool", len(pool))

spy = pd.read_parquet(os.path.join(PX, "SPY.parquet")); cal = spy.index
ma200 = spy["Close"].rolling(200).mean()
dates = [cal[cal.searchsorted(pd.Timestamp(y, m, 1))] for y in range(2011, 2026) for m in (1, 4, 7, 10)]
pxs = {t: pd.read_parquet(os.path.join(PX, f"{t}.parquet")).reindex(cal) for t in pool}
rows = []
for d in dates:
    pos = cal.get_loc(d)
    reg = "up" if spy["Close"].iloc[pos - 1] > ma200.iloc[pos - 1] else "down"
    for t in pool:
        c = now2cik[t]; p = pxs[t]
        px0 = p["RawClose"].iloc[pos - 1]
        if px0 != px0: continue
        s0, s1 = snap(c, d), snap(c, d - pd.Timedelta(days=365))
        mc = px0 * s0["SH"] if s0["SH"] == s0["SH"] else np.nan
        r3 = rev(c, d - pd.Timedelta(days=3 * 365))
        fs_parts = [s0["NI"] > 0 if s0["NI"] == s0["NI"] else None,
                    s0["CFO"] > 0 if s0["CFO"] == s0["CFO"] else None,
                    (s0["NI"] / s0["A"] > s1["NI"] / s1["A"]) if all(x == x and x for x in (s0["NI"], s0["A"], s1["NI"], s1["A"])) else None,
                    s0["CFO"] > s0["NI"] if s0["CFO"] == s0["CFO"] and s0["NI"] == s0["NI"] else None,
                    s0["LEV"] < s1["LEV"] if s0["LEV"] == s0["LEV"] and s1["LEV"] == s1["LEV"] else None,
                    s0["CR"] > s1["CR"] if s0["CR"] == s0["CR"] and s1["CR"] == s1["CR"] else None,
                    s0["SH"] <= s1["SH"] if s0["SH"] == s0["SH"] and s1["SH"] == s1["SH"] else None,
                    (s0["G"] / s0["R"] > s1["G"] / s1["R"]) if all(x == x and x for x in (s0["G"], s0["R"], s1["G"], s1["R"])) else None,
                    (s0["R"] / s0["A"] > s1["R"] / s1["A"]) if all(x == x and x for x in (s0["R"], s0["A"], s1["R"], s1["A"])) else None]
        av = [x for x in fs_parts if x is not None]
        fcf = s0["CFO"] - s0["CAPEX"] if s0["CFO"] == s0["CFO"] and s0["CAPEX"] == s0["CAPEX"] else np.nan
        ev = mc + s0["DEBT"] - (s0["CASH"] if s0["CASH"] == s0["CASH"] else 0) if mc == mc else np.nan
        ig = rdcf(ev, fcf)
        cagr = (s0["R"] / r3) ** (1 / 3) - 1 if r3 == r3 and r3 > 0 and s0["R"] == s0["R"] and s0["R"] > 0 else np.nan
        cl = p["Close"]
        fw = {}
        for n in (63, 252):
            e = pos + n
            fw[f"r{n}"] = cl.iloc[e] / cl.iloc[pos] - 1 if e < len(cal) and cl.iloc[e] == cl.iloc[e] and cl.iloc[pos] == cl.iloc[pos] else np.nan
        rows.append({"date": d, "t": t, "regime": reg, "mcap": mc,
                     "GPA": s0["G"] / s0["A"] if s0["A"] else np.nan,
                     "ACC": (s0["NI"] - s0["CFO"]) / s0["A"] if s0["A"] else np.nan,
                     "AG": s0["A"] / s1["A"] - 1 if s1["A"] and s1["A"] == s1["A"] else np.nan,
                     "ISS": s0["SH"] / s1["SH"] - 1 if s1["SH"] and s1["SH"] == s1["SH"] else np.nan,
                     "FS": sum(av) * 9 / len(av) if len(av) >= 8 else np.nan,
                     "EY": s0["NI"] / mc if mc and mc == mc else np.nan,
                     "FCFY": fcf / mc if mc and mc == mc else np.nan,
                     "RDCF": ig, "RGAP": ig - cagr if ig == ig and cagr == cagr else np.nan, **fw})
    print(d.date(), len(rows), flush=True)
pn = pd.DataFrame(rows)
pn.to_csv(os.path.join(DATA, "task5_panel.csv"), index=False)
print(pn.drop(columns=["date", "t", "regime"]).notna().mean().round(3).to_string())
print(pn[["GPA", "ACC", "AG", "ISS", "FS", "EY", "FCFY", "RDCF", "RGAP"]].describe().round(3).to_string())
