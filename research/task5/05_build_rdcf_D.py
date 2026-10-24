"""과제 5-05: 역DCF 정의 D (PLAN §7) — R 패널의 (날짜, 종목)마다 내재 성장률 g_D 계산.
입력: data/task5_panel_R.csv(유니버스·수익률), raw/sb/facts_rdcf.parquet, raw/mkt/DGS10.csv·ERPbymonth.xlsx, 가격.
출력: data/task5_panel_D.csv (R 패널 + RDCFD 와 구성요소)
"""
import os, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); MK = os.path.join(DATA, "raw", "mkt")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted")
DAY = np.timedelta64(1, "D")

# ---------- 재무 (최초 공시 값) ----------
f = pd.read_parquet(os.path.join(SB, "facts_rdcf.parquet"))
for c in ("start", "end", "filed"): f[c] = pd.to_datetime(f[c], errors="coerce")
f = f.dropna(subset=["end", "filed"]).sort_values("filed").drop_duplicates(["cik", "tag", "start", "end"], keep="first")
f["dur"] = (f["end"] - f["start"]).dt.days.astype(float)
F = {(c, t): (g["filed"].values, g["start"].values, g["end"].values, g["dur"].values, g["val"].values.astype(float))
     for (c, t), g in f.sort_values("filed").groupby(["cik", "tag"])}

def _rows(c, t, d):
    s = F.get((c, t))
    if s is None: return None
    k = np.searchsorted(s[0], np.datetime64(d), side="left")
    return None if k == 0 else [a[:k] for a in s]

def inst(c, t, d):
    r = _rows(c, t, d)
    if r is None: return np.nan
    fl, st, en, du, va = r; m = np.isnan(du)
    if not m.any(): return np.nan
    i = np.argmax(en[m])
    return va[m][i] if en[m][i] >= np.datetime64(d) - 200 * DAY else np.nan

def ttm(c, t, d):
    r = _rows(c, t, d)
    if r is None: return np.nan
    fl, st, en, du, va = r; ok = du >= 80
    if not ok.any(): return np.nan
    le = en[ok].max()
    if le < np.datetime64(d) - 200 * DAY: return np.nan
    cand = ok & (en == le) & (du <= 380)
    if not cand.any(): return np.nan
    j = np.where(cand)[0][np.argmax(du[cand])]; D = du[j]
    if 350 <= D <= 380: return va[j]
    if not (80 <= D <= 290): return np.nan
    fy = np.where((du >= 350) & (du <= 380) & (np.abs((en - (st[j] - DAY)) / DAY) <= 10))[0]
    py = np.where((np.abs(du - D) <= 10) & (np.abs((en - (le - 365 * DAY)) / DAY) <= 10))[0]
    if len(fy) == 0 or len(py) == 0: return np.nan
    return va[fy[-1]] + va[j] - va[py[-1]]

def first(*v):
    for x in v:
        if x == x: return x
    return np.nan
z = lambda x: 0.0 if x != x else x

def shares(c, d):
    for t in ("EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"):
        r = _rows(c, t, d)
        if r is None: continue
        m = r[0] >= np.datetime64(d) - 200 * DAY
        if m.any(): return r[4][m][-1]
    return np.nan

def fcf(c, d):
    cfo = ttm(c, "NetCashProvidedByUsedInOperatingActivities", d); cap = ttm(c, "PaymentsToAcquirePropertyPlantAndEquipment", d)
    if cfo != cfo or cap != cap: return np.nan
    sbc = first(ttm(c, "ShareBasedCompensation", d), ttm(c, "AllocatedShareBasedCompensationExpense", d), 0.0)
    return cfo - cap - sbc

# ---------- 시장 입력 ----------
rf = pd.read_csv(os.path.join(MK, "DGS10.csv")); rf.columns = ["date", "rf"]
rf["date"] = pd.to_datetime(rf["date"]); rf["rf"] = pd.to_numeric(rf["rf"], errors="coerce") / 100
rf = rf.dropna().set_index("date")["rf"]
erp = pd.read_excel(os.path.join(MK, "ERPbymonth.xlsx"))
erp = erp.assign(m=pd.to_datetime(erp["Start of month"])).set_index("m")["ERP (T12m)"].dropna()
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]
spym = spy.resample("ME").last().pct_change()

# ---------- 패널 ----------
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"])
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
now2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
pcache = {}
def price(t):
    if t not in pcache:
        p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
        pcache[t] = pd.read_parquet(p)[["Close", "RawClose", "RawUnadj"]].groupby(level=0).last() if os.path.exists(p) else None
    return pcache[t]

def beta(t, d):
    p = price(t)
    if p is None: return 1.0
    m = p["Close"].resample("ME").last().pct_change()
    lo = d - pd.DateOffset(months=60)
    x = pd.concat([m, spym], axis=1, keys=["s", "m"]).loc[lo:d - pd.Timedelta(days=1)].dropna()
    if len(x) < 24: return 1.0
    b = np.cov(x["s"], x["m"])[0, 1] / x["m"].var()
    return float(np.clip(0.67 * b + 0.33, 0.5, 2.0))

GT = 0.025
def solve(ev, f0, w):
    if not (ev == ev and f0 == f0 and w == w) or f0 <= 0 or ev <= 0 or w < GT + 0.01: return np.nan
    def val(g):
        v, cf = 0.0, f0
        for t in range(1, 11):
            gt = g if t <= 5 else g + (GT - g) * (t - 5) / 5
            cf *= 1 + gt; v += cf / (1 + w) ** t
        return v + cf * (1 + GT) / (w - GT) / (1 + w) ** 10
    lo, hi = -0.5, 1.0
    if val(lo) > ev: return lo
    if val(hi) < ev: return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if val(mid) < ev else (lo, mid)
    return (lo + hi) / 2

out = []
for i, r in enumerate(pn.itertuples()):
    c = now2cik.get(r.t) if not r.t.startswith("D:") else d2cik.get(r.t)
    d = r.date
    rec = {"date": d, "t": r.t}
    if c is None or c != c:
        out.append(rec); continue
    c = int(c); p = price(r.t)
    px0 = p["RawUnadj"].loc[:d - pd.Timedelta(days=1)].iloc[-1] if p is not None and len(p.loc[:d - pd.Timedelta(days=1)]) else np.nan
    sh = shares(c, d); E = px0 * sh if sh == sh else np.nan
    debt = z(first(inst(c, "LongTermDebtNoncurrent", d), inst(c, "LongTermDebt", d))) + \
           z(first(inst(c, "LongTermDebtCurrent", d), inst(c, "DebtCurrent", d))) + z(inst(c, "ShortTermBorrowings", d))
    lease = z(inst(c, "OperatingLeaseLiability", d)) + z(inst(c, "FinanceLeaseLiability", d))
    cash = z(inst(c, "CashAndCashEquivalentsAtCarryingValue", d)) + z(first(inst(c, "ShortTermInvestments", d), inst(c, "MarketableSecuritiesCurrent", d)))
    ev = E + debt + lease + z(inst(c, "MinorityInterest", d)) - cash if E == E else np.nan
    f0 = fcf(c, d); f1 = fcf(c, d - pd.Timedelta(days=365)); f2 = fcf(c, d - pd.Timedelta(days=730))
    norm = False
    if f0 == f0 and f1 == f1 and f2 == f2:
        avg = (f0 + f1 + f2) / 3
        if avg != 0 and abs(f0 - avg) / abs(avg) > 0.5:
            f0, norm = avg, True
    rfd = rf.loc[:d - pd.Timedelta(days=1)].iloc[-1]
    e_ = erp.loc[:d].iloc[-1] if len(erp.loc[:d]) else np.nan
    b = beta(r.t, d); ke = rfd + b * e_
    D = debt + lease
    ie = ttm(c, "InterestExpense", d)
    kd = float(np.clip(ie / debt, rfd, rfd + 0.06)) if ie == ie and debt > 0 else rfd + 0.015
    tax = 0.35 if d.year <= 2017 else 0.21
    w = (E * ke + D * kd * (1 - tax)) / (E + D) if E == E and E + D > 0 else np.nan
    g = solve(ev, f0, w)
    rec.update({"E": E, "EV": ev, "FCF0": f0, "fcf_norm": norm, "beta": b, "rf": rfd, "erp": e_, "ke": ke, "kd": kd, "wacc": w, "RDCFD": g})
    out.append(rec)
    if i % 5000 == 0: print(i, len(pn), flush=True)
o = pd.DataFrame(out)
pnD = pn.merge(o, on=["date", "t"], how="left")
pnD.to_csv(os.path.join(DATA, "task5_panel_D.csv"), index=False)
print("RDCFD coverage", round(pnD["RDCFD"].notna().mean(), 3), "| old RDCF coverage", round(pnD["RDCF"].notna().mean(), 3))
print(pnD[["beta", "wacc", "RDCFD"]].describe().round(3).to_string())
print("rank corr RDCFD vs RDCF (mean by date):", round(np.nanmean([g[["RDCFD", "RDCF"]].rank().corr().iloc[0, 1] for _, g in pnD.groupby("date")]), 3))
