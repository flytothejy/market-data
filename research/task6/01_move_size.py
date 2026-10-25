"""과제 6-01: 실적 발표일 변동폭 크기 예측 (PLAN.md 규칙 그대로)."""
import os, json, time, datetime
import numpy as np, pandas as pd, requests
import statsmodels.api as sm
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); CF = os.path.join(SB, "companyfacts")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task6", "out")
os.makedirs(OUT, exist_ok=True)
E = pd.read_csv(os.path.join(DATA, "events_R.csv"), parse_dates=["date", "rday"]).sort_values(["t", "rday"]).reset_index(drop=True)
E["y"] = E["abret"].abs()

# ---------- SIC ----------
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
now2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}; S = requests.Session(); S.headers.update(H)
def sic(cik):
    if cik is None or cik != cik: return None
    cik = int(cik); p = os.path.join(CF, f"{cik}_sub.json")
    if not os.path.exists(p):
        r = S.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", timeout=60); time.sleep(0.12)
        open(p, "w").write(r.text if r.status_code == 200 else "{}")
    try: return str(json.load(open(p)).get("sic") or "")[:2] or None
    except Exception: return None
tick = E["t"].unique()
SIC = {t: sic(d2cik.get(t) if t.startswith("D:") else now2cik.get(t)) for t in tick}
E["sic2"] = E["t"].map(SIC)

# ---------- 특징 ----------
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; sr = spy.pct_change()
E["_pos"] = cal.searchsorted(E["rday"].values)
for c in ("f1", "f2", "f4", "base_ratio"): E[c] = np.nan
for t, g in E.groupby("t"):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    if not os.path.exists(p): continue
    cl = pd.read_parquet(p)["Close"].groupby(level=0).last().reindex(cal)
    ab = (cl.pct_change(fill_method=None) - sr).values; lc = np.log(cl.values); ls = np.log(spy.values)
    ys = g["y"].values
    for k, (pos, i) in enumerate(zip(g["_pos"].values, g.index.values)):
        past = ys[max(0, k - 8):k]
        if len(past) >= 4: E.at[i, "f1"] = np.log(past.mean())
        w = ab[max(0, pos - 61):pos - 1]; w = w[np.isfinite(w)]
        if len(w) >= 40:
            E.at[i, "f2"] = np.log(w.std())
            med = np.median(np.abs(w))
            if med > 0: E.at[i, "base_ratio"] = E.at[i, "y"] / med
        e, s = pos - 1, pos - 21
        if s >= 0 and np.isfinite(lc[s]) and np.isfinite(lc[e]):
            E.at[i, "f4"] = np.log1p(abs((np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)))
# f3: 같은 SIC2, 반응일 전 90일, 다른 종목, 최소 5건 (없으면 전체 평균)
E = E.sort_values("rday").reset_index(drop=True)
rd = E["rday"].values; yv = E["y"].values; tv = E["t"].values; sv = E["sic2"].values
f3 = np.full(len(E), np.nan)
for i in range(len(E)):
    lo = np.searchsorted(rd, rd[i] - np.timedelta64(90, "D")); hi = np.searchsorted(rd, rd[i])
    if hi <= lo: continue
    m_all = tv[lo:hi] != tv[i]
    m = m_all & (sv[lo:hi] == sv[i]) if sv[i] is not None else np.zeros(hi - lo, bool)
    vals = yv[lo:hi][m] if m.sum() >= 5 else yv[lo:hi][m_all]
    if len(vals): f3[i] = np.log(vals.mean())
E["f3"] = f3; E["f5"] = np.log(E["dv252"]); E["f6"] = (E["timing"] == "AMC").astype(float)
E["q"] = E["rday"].dt.to_period("Q").astype(str)
E["ly"] = np.log(E["y"] + 0.001)
F = ["f1", "f2", "f3", "f4", "f5", "f6"]
D = E.dropna(subset=["f1", "f2", "cell"] + F).copy()

# ---------- 모델 (설계 칸만) ----------
dz = D[D["cell"] == "설계"]
m = sm.OLS(dz["ly"], sm.add_constant(dz[F])).fit()
json.dump({"params": m.params.to_dict(), "r2": m.rsquared, "n": int(m.nobs)}, open(os.path.join(OUT, "model.json"), "w"), indent=1)
D["pM"] = m.predict(sm.add_constant(D[F])); D["pB1"] = D["f1"]

def per_q(df, col):
    out = []
    for q, g in df.groupby("q"):
        if len(g) < 30: continue
        rho = stats.spearmanr(g[col], g["y"]).correlation
        top_p = g[col] >= g[col].quantile(0.8); top_y = g["y"] >= g["y"].quantile(0.8)
        out.append({"q": q, "rho": rho, "hit": (top_p & top_y).sum() / top_p.sum()})
    return pd.DataFrame(out).set_index("q")

def onesided(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))); return x.mean(), 1 - stats.t.cdf(t, len(x) - 1), len(x)

rows, logs = [], []
today = datetime.date.today().isoformat()
TESTS = [("B1_vs_0_rho", "pB1", None, "rho", 0.0), ("B1_vs_0_hit", "pB1", None, "hit", 0.2),
         ("M_vs_B1_rho", "pM", "pB1", "rho", None), ("M_vs_B1_hit", "pM", "pB1", "hit", None)]
for name, a, b, met, null in TESTS:
    res = {}
    for c in ("설계", "확인1", "확인2", "최종"):
        if c == "최종" and not all(res[x]["diff"] > 0 and res[x]["p1"] < 0.05 for x in ("확인1", "확인2")): break
        sub = D[D["cell"] == c]
        A = per_q(sub, a)[met]
        d = A - (per_q(sub, b)[met] if b else null)
        mu, p, nq = onesided(d.values)
        res[c] = {"a_mean": A.mean(), "diff": mu, "p1": p, "quarters": nq, "events": len(sub)}
    for c, r in res.items():
        rows.append({"test": name, "cell": c, **r})
        logs.append([f"T6-{name}-{c}", today, 6, "실적 발표일 변동폭 크기 예측", "MoveSize", name, "|abret|", c, r["events"],
                     "diff", round(r["diff"], 5), "", "", round(r["p1"], 4), f"quarters={r['quarters']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)

# ---------- 참고 ----------
E.to_csv(os.path.join(DATA, "task6_events.csv"), index=False)
ref = {"base_ratio_median": float(E["base_ratio"].median()), "base_ratio_p75": float(E["base_ratio"].quantile(.75)),
       "y_median": float(E["y"].median()), "events_used": int(len(D)), "model_r2_design": m.rsquared}
D["era"] = pd.cut(D["rday"].dt.year, [2004, 2012, 2019, 2030], labels=["2005-12", "2013-19", "2020~"]).astype(str)
split = []
for col in ("era", "regime"):
    for v, g in D.groupby(col):
        split.append({"split": col, "value": v, "rho_M": per_q(g, "pM")["rho"].mean(), "rho_B1": per_q(g, "pB1")["rho"].mean(),
                      "hit_M": per_q(g, "pM")["hit"].mean(), "hit_B1": per_q(g, "pB1")["hit"].mean()})
pd.DataFrame(split).to_csv(os.path.join(OUT, "splits.csv"), index=False)
json.dump(ref, open(os.path.join(OUT, "ref.json"), "w"), indent=1)
pd.set_option("display.width", 200, "display.float_format", "{:.4f}".format)
print(ref); print(m.params.round(3).to_dict()); print(res.to_string(index=False)); print(pd.DataFrame(split).to_string(index=False))
