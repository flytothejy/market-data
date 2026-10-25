"""과제 2-6-01: 행동주의 13D 표적 (PLAN.md 규칙 그대로)."""
import os, json, hashlib, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); CF = os.path.join(SB, "companyfacts")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task11", "out")
os.makedirs(OUT, exist_ok=True)
src = open(os.path.join(ROOT, "task5", "03_build_panel_R.py")).read().split("# ---------- 유니버스 ----------")[0]
gx = {"__file__": os.path.join(ROOT, "task5", "03_build_panel_R.py")}; exec(src, gx); inst, first_ok = gx["inst"], gx["first_ok"]
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False); now2cik = dict(zip(cur["ticker"], cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
cik_of = lambda t: d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"])
pn["cik"] = [cik_of(t) for t in pn["t"]]; pn = pn[pn["cik"].notna()].copy(); pn["cik"] = pn["cik"].astype(int)
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
def lpx(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    return np.log(pd.read_parquet(p)["Close"].groupby(level=0).last().reindex(cal).values) if os.path.exists(p) else None

# ---------- 사건: 행동주의 원본 13D가 회사 제출 이력에 있음 ----------
A = pd.read_csv(os.path.join(ROOT, "task11", "activist_13d.csv")); acc = dict(zip(A["acc"], A["fund"]))
ev = []
for c in pn["cik"].unique():
    p = os.path.join(CF, f"{c}_sub.json")
    if not os.path.exists(p): continue
    j = json.load(open(p)); parts = [j.get("filings", {}).get("recent", {})]
    for fo in j.get("filings", {}).get("files", []):
        fp = os.path.join(CF, f"{c}_{fo['name']}")
        if os.path.exists(fp): parts.append(json.load(open(fp)))
    for pt in parts:
        for a, fm, d in zip(pt.get("accessionNumber", []), pt.get("form", []), pt.get("filingDate", [])):
            if a in acc: ev.append({"cik": int(c), "date": pd.Timestamp(d), "fund": acc[a], "acc": a})
E = pd.DataFrame(ev).drop_duplicates("acc").sort_values(["cik", "date"])
keep, last = [], {}
for r in E.itertuples():
    if r.cik in last and (r.date - last[r.cik]).days <= 365: continue
    keep.append(r.Index); last[r.cik] = r.date
E = E.loc[keep]; E.to_csv(os.path.join(OUT, "events.csv"), index=False)
print("activist campaigns in universe:", len(E), "firms", E["cik"].nunique()); print(E.groupby("fund").size().sort_values(ascending=False).head(12).to_dict())

# ---------- 가. 반응 ----------
tk_of = pn.sort_values("t").groupby("cik")["t"].first().to_dict()
rows = []
for r in E.itertuples():
    lc = lpx(tk_of[r.cik])
    if lc is None: continue
    pos = cal.searchsorted(r.date)
    def car(a, b):
        s, e = pos + a - 1, pos + b
        if s < 0 or e >= len(cal) or not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
        return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
    rows.append({"cik": r.cik, "date": r.date, "fund": r.fund, "c_m1p1": car(-1, 1), "c_m20m2": car(-20, -2), "c_p2p250": car(2, 250)})
ES = pd.DataFrame(rows); ES.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
evs = {c: {"n": int(ES[c].notna().sum()), "mean": ES[c].mean(), "median": ES[c].median(), "pos": (ES[c] > 0).mean()} for c in ("c_m1p1", "c_m20m2", "c_p2p250")}
print("event study:", json.dumps(evs, default=float))

# ---------- 나. 표본 ----------
pn = pn[pn["date"] <= "2024-10-01"].sort_values(["date", "t"]).drop_duplicates(["cik", "date"]).copy()
evd = E.groupby("cik")["date"].apply(list).to_dict()
def lab(c, d):
    ds = evd.get(c, [])
    return int(any(d < x <= d + pd.Timedelta(days=365) for x in ds)), any(d - pd.Timedelta(days=365) < x <= d for x in ds)
L = [lab(c, d) for c, d in zip(pn["cik"], pn["date"])]
pn["y"] = [a for a, _ in L]; pn = pn[[not b for _, b in L]].copy()
cache = {}; xr, xr3, xc, xl = [], [], [], []
for r in pn.itertuples():
    if r.t not in cache: cache[r.t] = lpx(r.t)
    lc = cache[r.t]; e = cal.searchsorted(r.date) - 1
    def ex(n):
        s = e - n
        if lc is None or s < 0 or not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
        return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
    xr.append(ex(252)); xr3.append(ex(756))
    a = inst(r.cik, "Assets", r.date); cash = inst(r.cik, "CashAndCashEquivalentsAtCarryingValue", r.date)
    debt = first_ok(inst(r.cik, "LongTermDebtNoncurrent", r.date), inst(r.cik, "LongTermDebt", r.date))
    xc.append(cash / a if a and a == a and cash == cash else np.nan); xl.append(debt / a if a and a == a and debt == debt else np.nan)
pn["x_ret"], pn["x_ret3"], pn["x_cash"], pn["x_lev"] = xr, xr3, xc, xl
pn["x_size"] = np.log(pn["mcap"].where(pn["mcap"] > 0)); pn["x_ey"], pn["x_fcfy"], pn["x_ag"] = pn["EY"], pn["FCFY"], pn["AG"]
pn = pn.replace([np.inf, -np.inf], np.nan)
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
pn["grp"] = [("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") if t.startswith("D:") else grp.get(t) for t in pn["t"]]
pn = pn[pn["grp"].notna()].copy()
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
pn["cell"] = [names[(g, y % 2)] for g, y in zip(pn["grp"], pn["date"].dt.year)]
X = ["x_ret", "x_size", "x_ey", "x_fcfy", "x_cash", "x_lev", "x_ag", "x_ret3"]
dz = pn[pn["cell"] == "설계"]
for c in ("x_ret", "x_ey", "x_fcfy", "x_ag", "x_ret3", "x_cash", "x_lev"):
    lo, hi = dz[c].quantile([0.01, 0.99]); pn[c] = pn[c].clip(lo, hi)
dz = pn[pn["cell"] == "설계"]; med = dz[X].median()
pn["pB1"] = -pn["x_ret"].fillna(med["x_ret"])
for c in X:
    pn[f"m_{c}"] = pn[c].isna().astype(float); pn[c] = pn[c].fillna(med[c])
MF = [c for c in X + [f"m_{c}" for c in X] if pn.loc[pn["cell"] == "설계", c].std() > 0]
dz = pn[pn["cell"] == "설계"]
m = sm.Logit(dz["y"], sm.add_constant(dz[MF])).fit(disp=0, maxiter=300)
pn["pM"] = m.predict(sm.add_constant(pn[MF], has_constant="add"))
json.dump({"M": m.params.to_dict(), "base_design": float(dz["y"].mean())}, open(os.path.join(OUT, "model.json"), "w"), indent=1)
pn.to_csv(os.path.join(DATA, "task11_panel.csv"), index=False)

def top10(df, col):
    k = df[col] >= df.groupby("date")[col].transform(lambda x: x.quantile(0.9)); return df.loc[k, "y"].mean()
rng = np.random.default_rng(20261025)
def boot(df, fn, B=2000):
    by = {d: g for d, g in df.groupby("date")}; ds = list(by); out = []
    for _ in range(B):
        try: out.append(fn(pd.concat([by[d] for d in rng.choice(ds, len(ds))])))
        except ValueError: pass
    return np.array(out)
T = {"B1_auc": (lambda d: roc_auc_score(d["y"], d["pB1"]), 0.5),
     "M_minus_B1_auc": (lambda d: roc_auc_score(d["y"], d["pM"]) - roc_auc_score(d["y"], d["pB1"]), 0.0),
     "M_minus_B1_top10": (lambda d: top10(d, "pM") - top10(d, "pB1"), 0.0)}
rows, logs = [], []; today = datetime.date.today().isoformat()
for name, (fn, null) in T.items():
    res = {}
    for c in ("설계", "확인1", "확인2", "최종"):
        if c == "최종" and not all(res[x]["p1"] < 0.05 and res[x]["est"] > null for x in ("확인1", "확인2")): break
        sub = pn[pn["cell"] == c]; est = fn(sub); bs = boot(sub, fn)
        res[c] = {"est": est, "p1": float((bs <= null).mean()), "n": len(sub), "events": int(sub["y"].sum()), "base": sub["y"].mean(),
                  "auc_B1": roc_auc_score(sub["y"], sub["pB1"]), "auc_M": roc_auc_score(sub["y"], sub["pM"]), "top10_B1": top10(sub, "pB1"), "top10_M": top10(sub, "pM")}
    for c, r in res.items():
        rows.append({"test": name, "cell": c, **r})
        logs.append([f"T11-{name}-{c}", today, 11, "행동주의 13D 12개월 표적", "ACTIVIST", name, "13d12m", c, r["n"], name,
                     round(r["est"], 5), null, "", round(r["p1"], 4), f"events={r['events']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
R = pd.DataFrame(rows); R.to_csv(os.path.join(OUT, "results.csv"), index=False)
pn["era"] = pd.cut(pn["date"].dt.year, [2010, 2015, 2020, 2030], labels=["2011-15", "2016-20", "2021~"]).astype(str)
sp = [{"split": s, "value": v, "events": int(g["y"].sum()), "auc_B1": roc_auc_score(g["y"], g["pB1"]), "auc_M": roc_auc_score(g["y"], g["pM"]),
       "top10_B1": top10(g, "pB1"), "top10_M": top10(g, "pM")} for s in ("era", "regime") for v, g in pn.groupby(s) if g["y"].nunique() == 2]
pd.DataFrame(sp).to_csv(os.path.join(OUT, "splits.csv"), index=False)
pd.set_option("display.width", 250, "display.float_format", "{:.4f}".format)
print(R.to_string(index=False)); print(pd.DataFrame(sp).to_string(index=False)); print({k: round(v, 3) for k, v in m.params.items()})
