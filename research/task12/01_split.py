"""과제 2-7-01: 주식분할 예측 (PLAN.md 규칙 그대로)."""
import os, json, hashlib, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task12", "out")
os.makedirs(OUT, exist_ok=True)
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False); now2cik = dict(zip(cur["ticker"], cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
cik_of = lambda t: d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"])
pn["cik"] = [cik_of(t) for t in pn["t"]]; pn = pn[pn["cik"].notna()].copy(); pn["cik"] = pn["cik"].astype(int)
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
def pxs(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    return pd.read_parquet(p).groupby(level=0).last().reindex(cal) if os.path.exists(p) else None

SP = pd.read_csv(os.path.join(DATA, "raw", "eodhd", "splits_R.csv"), parse_dates=["date"])
SP["cik"] = [cik_of(t) for t in SP["t"]]; SP = SP[SP["cik"].notna()]; SP["cik"] = SP["cik"].astype(int)
SP = SP.drop_duplicates(["cik", "date"])
FW = SP[SP["ratio"] >= 1.5].sort_values(["cik", "date"])
fwd = FW.groupby("cik")["date"].apply(list).to_dict()
print("forward splits:", len(FW), "firms", FW["cik"].nunique(), "| 2011+:", int((FW["date"] >= "2011-01-01").sum()))

# ---------- 가. 반응 (효력일) ----------
tk_of = pn.sort_values("t").groupby("cik")["t"].first().to_dict()
rows = []
for r in FW[(FW["date"] >= "2006-01-01")].itertuples():
    if r.cik not in tk_of: continue
    px = pxs(tk_of[r.cik])
    if px is None: continue
    lc = np.log(px["Close"].values); pos = cal.searchsorted(r.date)
    def car(a, b):
        s, e = pos + a - 1, pos + b
        if s < 0 or e >= len(cal) or not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
        return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
    rows.append({"cik": r.cik, "t": tk_of[r.cik], "date": r.date, "ratio": r.ratio, "c_m60m2": car(-60, -2), "c_m1p1": car(-1, 1), "c_p2p250": car(2, 250)})
ES = pd.DataFrame(rows); ES.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
evs = {c: {"n": int(ES[c].notna().sum()), "mean": ES[c].mean(), "median": ES[c].median(), "pos": (ES[c] > 0).mean()} for c in ("c_m60m2", "c_m1p1", "c_p2p250")}
print("event study:", json.dumps(evs, default=float))

# ---------- 나. 표본·특징 ----------
pn = pn[pn["date"] <= "2024-10-01"].sort_values(["date", "t"]).drop_duplicates(["cik", "date"]).copy()
ys, drop = [], []
for c, d in zip(pn["cik"], pn["date"]):
    ds = fwd.get(c, [])
    ys.append(int(any(d + pd.Timedelta(days=90) < x <= d + pd.Timedelta(days=365) for x in ds)))
    drop.append(any(d < x <= d + pd.Timedelta(days=90) for x in ds) or any(d - pd.Timedelta(days=365) < x <= d for x in ds))
pn["y"] = ys; pn = pn[[not x for x in drop]].copy()
cache = {}; F = {k: [] for k in ("lp", "x_ret1", "x_ret3", "x_nsplit", "x_since")}
for r in pn.itertuples():
    if r.t not in cache: cache[r.t] = pxs(r.t)
    px = cache[r.t]; e = cal.searchsorted(r.date) - 1
    if px is None:
        for k in ("lp", "x_ret1", "x_ret3"): F[k].append(np.nan)
    else:
        u = px["RawUnadj"].iloc[e]; F["lp"].append(np.log(u) if u == u and u > 0 else np.nan)
        lc = np.log(px["Close"].values)
        for k, n in (("x_ret1", 252), ("x_ret3", 756)):
            s = e - n
            F[k].append((np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1) if s >= 0 and np.isfinite(lc[s]) and np.isfinite(lc[e]) else np.nan)
    past = [x for x in fwd.get(r.cik, []) if x <= r.date]
    F["x_nsplit"].append(float(sum(x > r.date - pd.Timedelta(days=3652) for x in past)))
    F["x_since"].append(min((r.date - past[-1]).days / 365.25, 15) if past else 15.0)
for k, v in F.items(): pn[k] = v
pn["x_size"] = np.log(pn["mcap"].where(pn["mcap"] > 0))
pn["x_px_rel"] = pn["lp"] - pn.groupby("date")["lp"].transform("median")
pn = pn.replace([np.inf, -np.inf], np.nan)
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
pn["grp"] = [("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") if t.startswith("D:") else grp.get(t) for t in pn["t"]]
pn = pn[pn["grp"].notna()].copy()
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
pn["cell"] = [names[(g, y % 2)] for g, y in zip(pn["grp"], pn["date"].dt.year)]
X = ["lp", "x_ret1", "x_ret3", "x_size", "x_nsplit", "x_since", "x_px_rel"]
dz = pn[pn["cell"] == "설계"]
for c in ("x_ret1", "x_ret3"):
    lo, hi = dz[c].quantile([0.01, 0.99]); pn[c] = pn[c].clip(lo, hi)
dz = pn[pn["cell"] == "설계"]; med = dz[X].median()
pn["pB1"] = pn["lp"].fillna(med["lp"])
for c in X:
    pn[f"m_{c}"] = pn[c].isna().astype(float); pn[c] = pn[c].fillna(med[c])
MF = [c for c in X + [f"m_{c}" for c in X] if pn.loc[pn["cell"] == "설계", c].std() > 0]
dz = pn[pn["cell"] == "설계"]
m = sm.Logit(dz["y"], sm.add_constant(dz[MF])).fit(disp=0, maxiter=300)
pn["pM"] = m.predict(sm.add_constant(pn[MF], has_constant="add"))
json.dump({"M": m.params.to_dict(), "base_design": float(dz["y"].mean())}, open(os.path.join(OUT, "model.json"), "w"), indent=1)
pn.to_csv(os.path.join(DATA, "task12_panel.csv"), index=False)

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
        logs.append([f"T12-{name}-{c}", today, 12, "주식분할 예측(90~365일)", "SPLIT", name, "split", c, r["n"], name,
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
