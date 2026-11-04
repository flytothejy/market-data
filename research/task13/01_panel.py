"""과제 2-8-01: 체크리스트 신호 패널 + 다음 실적 결과 (PLAN.md §2~4).

입력(R2 사본, 환경변수 R2DL 폴더): facts.parquet, facts_supp.parquet, company.parquet,
filings.parquet, px_YYYY.parquet  /  research/data: universe.csv, earnings_raw.csv, split_groups.csv
출력: task13/out/panel.parquet
"""
import os, glob
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "task13", "out")
R2 = os.environ["R2DL"]
os.makedirs(OUT, exist_ok=True)

# ---------- 유니버스 ----------
uni = pd.read_csv(os.path.join(DATA, "universe.csv"))
uni = uni[~uni["sec"].isin(["Financial Services", "Real Estate"])]
co = pd.read_parquet(os.path.join(R2, "company.parquet"))
co = co[co["ticker"].isin(uni["t"])].drop_duplicates("cik")
cik2t = dict(zip(co["cik"], co["ticker"]))

# ---------- 재무 ----------
f = pd.concat([pd.read_parquet(os.path.join(R2, "facts.parquet")), pd.read_parquet(os.path.join(R2, "facts_supp.parquet"))])
f = f[f["cik"].isin(cik2t) & f["form"].isin(["10-Q", "10-K", "10-Q/A", "10-K/A"]) & (f["unit"].isin(["USD", "shares"]))]
f["end"] = pd.to_datetime(f["end"]); f["start"] = pd.to_datetime(f["start"]); f["filed"] = pd.to_datetime(f["filed"])
f["days"] = (f["end"] - f["start"]).dt.days

REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"]


def first_reported(x):
    """같은 (end[, start])의 최초 공시값과 최초 공시일."""
    return x.sort_values("filed").drop_duplicates([c for c in ["start", "end"] if x[c].notna().any()], keep="first")


def instant(g, tags):
    acc = None
    for t in tags:
        x = g[g["tag"] == t]
        if len(x):
            x = x.sort_values("filed").drop_duplicates("end", keep="first").set_index("end")[["val", "filed"]]
            acc = x if acc is None else acc.combine_first(x)
    return acc


def quarterly_duration(g, tags, derive_q4=True, ytd=False):
    """태그 우선순위대로 분기 말마다 값을 합친다 (변경 이력 2: 첫 태그만 쓰던 오류 수정)."""
    acc = None
    for t in tags:
        q = _qdur(g, [t], derive_q4, ytd)
        if q is not None:
            acc = q if acc is None else acc.combine_first(q)
    return acc if acc is not None and len(acc) >= 4 else None


def _qdur(g, tags, derive_q4=True, ytd=False):
    """3개월 값. ytd=True면 같은 시작일 누적값의 차분으로 분기값을 만든다. derive_q4: 연간 − 3개 분기."""
    for t in tags:
        x = g[g["tag"] == t]
        if x.empty:
            continue
        x = x.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
        q = x[x["days"].between(80, 100)].set_index("end")[["val", "filed"]]
        q = q[~q.index.duplicated()]
        if ytd:
            rows = {}
            for s, y in x[x["days"] > 100].groupby("start"):
                y = y.sort_values("end")
                prev = None
                for _, r in y.iterrows():
                    if prev is None:
                        if 80 <= r["days"] <= 100:
                            pass
                    else:
                        rows[r["end"]] = (r["val"] - prev["val"], r["filed"])
                    prev = r
            # 첫 분기(3개월 누적)
            for s, y in x[x["days"].between(80, 100)].groupby("start"):
                for _, r in y.iterrows():
                    rows.setdefault(r["end"], (r["val"], r["filed"]))
            if rows:
                q2 = pd.DataFrame.from_dict(rows, orient="index", columns=["val", "filed"])
                q = q2.combine_first(q) if len(q) else q2
        if derive_q4:
            ann = x[x["days"].between(350, 380)]
            add = {}
            for _, a in ann.iterrows():
                if a["end"] in q.index:
                    continue
                inq = q[(q.index > a["start"]) & (q.index < a["end"])]
                if len(inq) == 3:
                    add[a["end"]] = (a["val"] - inq["val"].sum(), a["filed"])
            if add:
                q = pd.concat([q, pd.DataFrame.from_dict(add, orient="index", columns=["val", "filed"])])
        q = q.sort_index()
        if len(q) >= 4:
            return q
    return None


def near(s, e, lo, hi):
    """s 인덱스 중 e보다 lo~hi일 앞선 값."""
    if s is None:
        return None
    c = s[(s.index <= e - pd.Timedelta(days=lo)) & (s.index >= e - pd.Timedelta(days=hi))]
    return c.iloc[-1] if len(c) else None


rows = []
for cik, g in f.groupby("cik"):
    rev = quarterly_duration(g, REV)
    if rev is None:
        continue
    ar = instant(g, ["AccountsReceivableNetCurrent"])
    inv = instant(g, ["InventoryNet"])
    ltds = [instant(g, ["LongTermDebt"]), instant(g, ["LongTermDebtNoncurrent"])]  # 같은 태그끼리만 비교
    ni = quarterly_duration(g, ["NetIncomeLoss", "ProfitLoss"], ytd=True)
    cfo = quarterly_duration(g, ["NetCashProvidedByUsedInOperatingActivities"], ytd=True)
    sh = quarterly_duration(g, ["WeightedAverageNumberOfDilutedSharesOutstanding"], derive_q4=False)
    for e, r in rev.iterrows():
        F = r["filed"]
        rp = near(rev["val"], e, 350, 380)
        d = {"cik": cik, "t": cik2t[cik], "E": e, "F": F}
        rg = (r["val"] / rp - 1) if (rp is not None and rp > 0 and r["val"] > 0) else np.nan
        d["rev_g"] = rg
        for nm, s in [("ar", ar), ("inv", inv)]:
            if s is not None and e in s.index and s.loc[e, "filed"] <= F + pd.Timedelta(days=5):
                p = near(s["val"], e, 350, 380)
                d[f"{nm}_g"] = (s.loc[e, "val"] / p - 1) if (p is not None and p > 0) else np.nan
            else:
                d[f"{nm}_g"] = np.nan
        d["ltd_qg"] = np.nan
        for ltd in ltds:
            if ltd is not None and e in ltd.index:
                p = near(ltd["val"], e, 80, 100)
                if p is not None and p > 0:
                    d["ltd_qg"] = ltd.loc[e, "val"] / p - 1
                    break
        d["cash_bad"] = float(cfo.loc[e, "val"] < ni.loc[e, "val"]) if (cfo is not None and ni is not None and e in cfo.index and e in ni.index) else np.nan
        if sh is not None and e in sh.index:
            p = near(sh["val"], e, 350, 380)
            d["iss_g"] = (sh.loc[e, "val"] / p - 1) if (p is not None and p > 0) else np.nan
        else:
            d["iss_g"] = np.nan
        rows.append(d)
P = pd.DataFrame(rows)
P = P[(P["F"] >= "2010-01-01") & (P["F"] <= "2026-10-31")]
# 변경 이력 1(결과 보기 전): 최초 공시가 분기 말 100일 넘어서면 나중 공시의 비교값 → 실시간 이벤트 아님, 제외
P = P[(P["F"] - P["E"]).dt.days <= 100]
# 변경 이력 1: 단위 오류 방지 범위 (밖이면 계산 불가로 둠)
for c, lo, hi in [("rev_g", -0.9, 5), ("ar_g", -0.9, 5), ("inv_g", -0.9, 5), ("ltd_qg", -0.95, 10), ("iss_g", -0.5, 1.0)]:
    P.loc[(P[c] <= lo) | (P[c] >= hi), c] = np.nan
P["ar_gap"] = P["ar_g"] - P["rev_g"]
P["inv_gap"] = P["inv_g"] - P["rev_g"]
P["AR"] = np.where(P["ar_gap"].notna(), (P["ar_gap"] > 0.10).astype(float), np.nan)
P["INV"] = np.where(P["inv_gap"].notna(), (P["inv_gap"] > 0.10).astype(float), np.nan)
P["DEBT"] = np.where(P["ltd_qg"].notna(), (P["ltd_qg"] > 0.05).astype(float), np.nan)
P["ISS"] = np.where(P["iss_g"].notna(), (P["iss_g"] > 0.02).astype(float), np.nan)
P["CASH"] = P["cash_bad"]
comp = P[["AR", "INV", "DEBT", "CASH", "ISS"]]
P["n_avail"] = comp.notna().sum(axis=1)
P["n_flag"] = comp.fillna(0).sum(axis=1)
P["COMP2"] = np.where(P["n_avail"] >= 3, (P["n_flag"] >= 2).astype(float), np.nan)
print("panel", len(P), "firms", P["t"].nunique())
P.to_parquet(os.path.join(OUT, "fund.parquet"))  # 과제 2-9(섹터) 재사용

# ---------- 가격 ----------
px = pd.concat([pd.read_parquet(p, columns=["date", "ticker", "close", "adj_close", "volume"]) for p in sorted(glob.glob(os.path.join(R2, "px_20*.parquet")))])
px["ticker"] = px["ticker"].str.replace("-", ".", regex=False)
px["date"] = pd.to_datetime(px["date"])
AC = px.pivot_table(index="date", columns="ticker", values="adj_close")
DV = px.assign(dv=px["close"] * px["volume"]).pivot_table(index="date", columns="ticker", values="dv")
cal = AC.index
spy = AC["SPY"]
spy_ma = spy.rolling(200).mean()
ADV = DV.rolling(252, min_periods=200).mean().shift(1)

# ---------- 실적 이벤트 (과제 1-1 규칙) ----------
er = pd.read_csv(os.path.join(DATA, "earnings_raw.csv"))
er["dt"] = pd.to_datetime(er["dt"])
er = er[er["eps_est"].notna() & er["eps_act"].notna()].copy()
er["date"] = er["dt"].dt.normalize()
er = er.sort_values(["t", "date"]).drop_duplicates(["t", "date"], keep="first")
mins = er["dt"].dt.hour * 60 + er["dt"].dt.minute
er["timing_yf"] = np.select([(mins > 0) & (mins < 570), mins >= 960], ["BMO", "AMC"], "UNK")
k8 = pd.read_parquet(os.path.join(R2, "filings.parquet"), columns=["ticker", "form", "items", "accepted"])
k8 = k8[(k8["form"] == "8-K") & k8["items"].fillna("").str.contains("2.02")].dropna(subset=["accepted"])
k8["acc"] = pd.to_datetime(k8["accepted"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
k8["kdate"] = k8["acc"].dt.normalize()
km = k8["acc"].dt.hour * 60 + k8["acc"].dt.minute
k8["timing_8k"] = np.select([km < 570, km >= 960], ["BMO", "AMC"], "INTRA")
k8 = k8.sort_values("kdate")[["ticker", "kdate", "timing_8k"]].rename(columns={"ticker": "t"})
er = er.sort_values("date")
er = pd.merge_asof(er, k8, left_on="date", right_on="kdate", by="t", direction="nearest", tolerance=pd.Timedelta(days=3))
has8 = er["kdate"].notna() & (er["timing_8k"] != "INTRA")
er.loc[has8, "date"] = er.loc[has8, "kdate"]
er["timing"] = np.where(has8, er["timing_8k"], er["timing_yf"])
er = er.sort_values(["t", "date"]).drop_duplicates(["t", "date"], keep="first").reset_index(drop=True)
dd = (er["eps_act"].round(2) - er["eps_est"].round(2)).round(2)
er["beat"] = (dd >= 0.01).astype(float)
er["b2"] = er.groupby("t")["beat"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).mean())
pos = cal.searchsorted(er["date"])
amc = (er["timing"] == "AMC").values & (pos < len(cal)) & (cal[np.minimum(pos, len(cal) - 1)] == er["date"].values)
pos = np.where(amc, pos + 1, pos)
ok = (er["timing"] != "UNK").values & (pos > 0) & (pos < len(cal))
er["rpos"] = np.where(ok, pos, -1)
er = er[er["rpos"] > 0]

RET = AC.pct_change(fill_method=None)
SR = spy.pct_change()


def cumab(t, i0, i1):
    """i0~i1 거래일(포함) 누적 수익 − SPY 누적 수익."""
    if t not in AC or i1 < i0:
        return np.nan
    a = AC[t].iloc[i0 - 1:i1 + 1]
    if a.isna().any():
        return np.nan
    return (a.iloc[-1] / a.iloc[0]) - (spy.iloc[i1] / spy.iloc[i0 - 1])


ers = {t: g.sort_values("rpos") for t, g in er.groupby("t")}
out = []
for _, r in P.iterrows():
    t = r["t"]
    if t not in ers or t not in AC:
        continue
    fpos = cal.searchsorted(r["F"])
    if fpos >= len(cal) - 2:
        continue
    g = ers[t]
    nx = g[g["rpos"] > fpos + 1]
    if nx.empty:
        continue
    n = nx.iloc[0]
    gap = int(n["rpos"]) - fpos
    if gap < 20 or gap > 140:
        continue
    rp = int(n["rpos"])
    y2 = RET[t].iloc[rp] - SR.iloc[rp] if pd.notna(RET[t].iloc[rp]) else np.nan
    i0, i1 = fpos + 2, min(rp - 1, fpos + 2 + 89)
    y3 = cumab(t, i0, i1)
    raw3 = (AC[t].iloc[i1] / AC[t].iloc[i0 - 1] - 1) if pd.notna(y3) else np.nan
    adv = ADV[t].iloc[fpos] if t in ADV else np.nan
    prev = spy.iloc[fpos - 1]
    reg = None if pd.isna(spy_ma.iloc[fpos - 1]) else ("up" if prev > spy_ma.iloc[fpos - 1] else "down")
    out.append({**r.to_dict(), "fday": cal[fpos], "rday": cal[rp], "gap": gap, "adv": adv, "regime": reg,
                "beat": n["beat"], "b2": n["b2"], "y2": y2, "y3": y3, "ret3": raw3})
X = pd.DataFrame(out)
X = X[X["adv"] >= 2e7]

# ---------- 4칸 ----------
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")).set_index("t")["grp"]
X["grp"] = X["t"].map(grp)
X["year"] = X["fday"].dt.year
yr_first = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[:10].max())
yr_last = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[-10:].min())
X["boundary"] = (X["fday"] <= X["year"].map(yr_first)) | (X["fday"] >= X["year"].map(yr_last))
par = np.where(X["year"] % 2 == 1, "odd", "even")
cellname = {("A", "odd"): "설계", ("A", "even"): "확인1", ("B", "odd"): "확인2", ("B", "even"): "최종"}
X["cell"] = [cellname.get((g_, p_)) if not b_ else None for g_, p_, b_ in zip(X["grp"], par, X["boundary"])]
X["era"] = pd.cut(X["year"], [2009, 2014, 2019, 2030], labels=["2010-14", "2015-19", "2020~"])
X.to_parquet(os.path.join(OUT, "panel.parquet"))
print("events", len(X), "firms", X["t"].nunique(), "cells", X["cell"].value_counts(dropna=False).to_dict())
print("flag rates", X[["AR", "INV", "DEBT", "CASH", "ISS", "COMP2"]].mean().round(3).to_dict())
