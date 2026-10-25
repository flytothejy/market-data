"""과제 2-5-01: 부실 경고 (PLAN.md 규칙 그대로)."""
import os, json, hashlib, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); CF = os.path.join(SB, "companyfacts")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task10", "out")
os.makedirs(OUT, exist_ok=True)
# 재무 함수: 과제 1-5 R 패널 코드(수정판)에 태그 3개를 더해 불러온다
src = open(os.path.join(ROOT, "task5", "03_build_panel_R.py")).read().split("# ---------- 유니버스 ----------")[0]
src = src.replace('"WeightedAverageNumberOfDilutedSharesOutstanding"]', '"WeightedAverageNumberOfDilutedSharesOutstanding", "RetainedEarningsAccumulatedDeficit", "OperatingIncomeLoss", "Liabilities"]', 1)
gx = {"__file__": os.path.join(ROOT, "task5", "03_build_panel_R.py")}; exec(src, gx)
inst, ttm, rev = gx["inst"], gx["ttm"], gx["rev"]
# R2 재무 자료에는 이익잉여금이 없고 상장폐지 회사 자료는 태그가 적다 → SEC 원본 companyfacts에서 세 태그를 직접 읽어 넣는다 (결과 보기 전 수정)
EXTRA = ("Liabilities", "RetainedEarningsAccumulatedDeficit", "OperatingIncomeLoss")
def load_extra(c):
    p = os.path.join(CF, f"{c}.json")
    try: j = json.load(open(p))
    except Exception: return
    ug = j.get("facts", {}).get("us-gaap", {})
    for tag in EXTRA:
        rows = [(pd.Timestamp(x["filed"]), pd.Timestamp(x["start"]) if "start" in x else pd.NaT, pd.Timestamp(x["end"]), x["val"])
                for x in ug.get(tag, {}).get("units", {}).get("USD", []) if "filed" in x and "end" in x]
        if not rows: continue
        g = pd.DataFrame(rows, columns=["filed", "start", "end", "val"]).sort_values("filed").drop_duplicates(["start", "end"], keep="first")
        g["dur"] = (g["end"] - g["start"]).dt.days
        gx["F"][(c, tag)] = (g["filed"].values, g["start"].values, g["end"].values, g["dur"].values.astype(float), g["val"].values.astype(float))

cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False); now2cik = dict(zip(cur["ticker"], cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"])); dstat = dict(zip("D:" + dm["code"], dm["status"]))
cik_of = lambda t: d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"])
pn["cik"] = [cik_of(t) for t in pn["t"]]; pn = pn[pn["cik"].notna()].copy(); pn["cik"] = pn["cik"].astype(int)
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
def pxs(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    return pd.read_parquet(p).groupby(level=0).last().reindex(cal) if os.path.exists(p) else None

# ---------- 사건 ----------
acq = set(pd.read_csv(os.path.join(ROOT, "task7", "out", "announcements.csv"))["t"])
ev, k103 = {}, []
for c, g in pn.groupby("cik"):
    p = os.path.join(CF, f"{c}_sub.json")
    if os.path.exists(p):
        j = json.load(open(p)); parts = [j.get("filings", {}).get("recent", {})]
        for fo in j.get("filings", {}).get("files", []):
            fp = os.path.join(CF, f"{c}_{fo['name']}")
            if os.path.exists(fp): parts.append(json.load(open(fp)))
        ds = [pd.Timestamp(d) for pt in parts for f, d, it in zip(pt.get("form", []), pt.get("filingDate", []), pt.get("items", [""] * len(pt.get("form", []))))
              if f == "8-K" and "1.03" in [x.strip() for x in (it or "").split(",")]]
        for d in sorted(set(ds)): k103.append({"cik": c, "t": g["t"].iloc[0], "date": d})
        if ds: ev[c] = min(ds)
    for t in g["t"].unique():
        if not t.startswith("D:") or t in acq or dstat.get(t) == "still_filing_other_ticker": continue
        px = pxs(t)
        if px is None: continue
        u = px["RawUnadj"].dropna(); cl = px["Close"].dropna()
        if len(u) < 20: continue
        last = u.index[-1]; r252 = cl.iloc[-1] / cl.iloc[max(0, len(cl) - 253)] - 1
        if u.iloc[-1] < 2 or r252 <= -0.7:
            ev[c] = min(ev.get(c, last), last)
EVD = pd.Series(ev, name="event").rename_axis("cik").reset_index(); EVD.to_csv(os.path.join(OUT, "events.csv"), index=False)
K = pd.DataFrame(k103); K.to_csv(os.path.join(OUT, "k103.csv"), index=False)
print("distress firms:", len(EVD), "| 8-K 1.03 filings:", len(K), "firms", K["cik"].nunique() if len(K) else 0)

# ---------- 가. 반응 ----------
rows = []
for r in K.drop_duplicates("cik").itertuples():
    keys = pn.loc[pn["cik"] == r.cik, "t"].unique()
    for t in keys:
        px = pxs(t)
        if px is None: continue
        lc = np.log(px["Close"].values); pos = cal.searchsorted(r.date)
        def car(a, b):
            s, e = pos + a - 1, pos + b
            if s < 0 or e >= len(cal) or not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
            return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
        v = {"cik": r.cik, "t": t, "date": r.date, "c_m1p1": car(-1, 1), "c_m60m2": car(-60, -2), "c_m250m2": car(-250, -2)}
        if np.isfinite(v["c_m1p1"]) or np.isfinite(v["c_m60m2"]): rows.append(v); break
ES = pd.DataFrame(rows); ES.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
evs = {c: {"n": int(ES[c].notna().sum()), "mean": ES[c].mean(), "median": ES[c].median()} for c in ("c_m1p1", "c_m60m2", "c_m250m2")}
print("event study:", json.dumps(evs, default=float))

# ---------- 나. 표본·특징 ----------
pn = pn[pn["date"] <= "2024-10-01"].sort_values(["date", "t"]).drop_duplicates(["cik", "date"])
evm = dict(zip(EVD["cik"], EVD["event"]))
pn["ev"] = pn["cik"].map(evm)
pn["y"] = ((pn["ev"] > pn["date"]) & (pn["ev"] <= pn["date"] + pd.Timedelta(days=365))).astype(int)
pn = pn[~((pn["ev"] <= pn["date"]) & (pn["ev"] > pn["date"] - pd.Timedelta(days=730)))]
for c in pn["cik"].unique(): load_extra(int(c))
print("extra tag series loaded:", sum(1 for k in gx["F"] if k[1] in EXTRA))
F = {k: [] for k in ("z", "nimta", "tlmta", "cashmta", "exret", "sigma", "price")}
cache = {}
for r in pn.itertuples():
    c, d, mc = r.cik, r.date, r.mcap
    A = inst(c, "Assets", d); TL = inst(c, "Liabilities", d); CA = inst(c, "AssetsCurrent", d); CL = inst(c, "LiabilitiesCurrent", d)
    RE = inst(c, "RetainedEarningsAccumulatedDeficit", d); EBIT = ttm(c, "OperatingIncomeLoss", d); S_ = rev(c, d)
    NI = ttm(c, "NetIncomeLoss", d); CASH = inst(c, "CashAndCashEquivalentsAtCarryingValue", d)
    ok = lambda *x: all(v == v for v in x)
    z = (1.2 * (CA - CL) / A + 1.4 * RE / A + 3.3 * EBIT / A + 0.6 * mc / TL + 1.0 * S_ / A) if ok(A, TL, CA, CL, RE, EBIT, S_, mc) and A > 0 and TL > 0 else np.nan
    mta = mc + TL if ok(mc, TL) else np.nan
    F["z"].append(z); F["nimta"].append(NI / mta if ok(NI, mta) and mta > 0 else np.nan)
    F["tlmta"].append(TL / mta if ok(TL, mta) and mta > 0 else np.nan); F["cashmta"].append(CASH / mta if ok(CASH, mta) and mta > 0 else np.nan)
    if r.t not in cache: cache[r.t] = pxs(r.t)
    px = cache[r.t]; pos = cal.searchsorted(d) - 1
    if px is None: F["exret"].append(np.nan); F["sigma"].append(np.nan); F["price"].append(np.nan); continue
    lc = np.log(px["Close"].values); s = pos - 252
    F["exret"].append((lc[pos] - lc[s]) - (ls[pos] - ls[s]) if s >= 0 and np.isfinite(lc[s]) and np.isfinite(lc[pos]) else np.nan)
    w = np.diff(lc[pos - 63:pos + 1]); w = w[np.isfinite(w)]
    F["sigma"].append(w.std() if len(w) >= 40 else np.nan)
    u = px["RawUnadj"].iloc[pos]; F["price"].append(np.log(min(u, 15)) if u == u and u > 0 else np.nan)
for k, v in F.items(): pn[k] = v
pn["rsize"] = np.log(pn["mcap"].where(pn["mcap"] > 0)); pn["nz"] = -pn["z"]
pn = pn.replace([np.inf, -np.inf], np.nan)   # 가격 0 등에서 생긴 무한대는 결측
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
pn["grp"] = [("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") if t.startswith("D:") else grp.get(t) for t in pn["t"]]
pn = pn[pn["grp"].notna()].copy()
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
pn["cell"] = [names[(g, y % 2)] for g, y in zip(pn["grp"], pn["date"].dt.year)]
X = ["nz", "nimta", "tlmta", "cashmta", "exret", "sigma", "rsize", "price"]
dz = pn[pn["cell"] == "설계"]
for c in X:
    lo, hi = dz[c].quantile([0.01, 0.99]); pn[c] = pn[c].clip(lo, hi)
dz = pn[pn["cell"] == "설계"]; med = dz[X].median()
pn["m_nz"] = pn["nz"].isna().astype(float); pn["pB1"] = pn["nz"].fillna(med["nz"])
for c in X:
    pn[f"m_{c}"] = pn[c].isna().astype(float); pn[c] = pn[c].fillna(med[c])
MF = X + [f"m_{c}" for c in X]
dz = pn[pn["cell"] == "설계"]; MF = [c for c in MF if dz[c].std() > 0]
m = sm.Logit(dz["y"], sm.add_constant(dz[MF])).fit(disp=0, maxiter=300)
pn["pM"] = m.predict(sm.add_constant(pn[MF], has_constant="add"))
json.dump({"M": m.params.to_dict(), "base_design": float(dz["y"].mean()), "n_events": int(pn["y"].sum())}, open(os.path.join(OUT, "model.json"), "w"), indent=1)
pn.to_csv(os.path.join(DATA, "task10_panel.csv"), index=False)

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
        logs.append([f"T10-{name}-{c}", today, 10, "부실 12개월 경고", "DISTRESS", name, "distress12m", c, r["n"], name,
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
