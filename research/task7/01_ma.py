"""과제 7-01: 피인수 예측 (PLAN.md 규칙 그대로). 정답 만들기 → 사건 연구(A) → 예측(B)."""
import os, json, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); CF = os.path.join(SB, "companyfacts")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task7", "out")
os.makedirs(OUT, exist_ok=True)
MA = {"PREM14A", "DEFM14A", "425", "SC TO-C", "SC14D9C", "SC 14D9", "SC TO-T"}

# ---------- 정답: 상장폐지 회사의 피인수 발표일 ----------
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); dm = dm[dm["status"].isin(["unique", "still_filing_other_ticker"])]
ix = pd.read_csv(os.path.join(DATA, "prices_delisted", "_index.csv")).set_index("code")
ann = {}
for r in dm.itertuples():
    p = os.path.join(CF, f"{int(r.cik)}_sub.json")
    if not os.path.exists(p) or r.code not in ix.index: continue
    j = json.load(open(p)); parts = [j.get("filings", {}).get("recent", {})]
    for fo in j.get("filings", {}).get("files", []):
        fp = os.path.join(CF, f"{int(r.cik)}_{fo['name']}")
        if os.path.exists(fp): parts.append(json.load(open(fp)))
    last = pd.Timestamp(ix.loc[r.code, "last"])
    fs, k8 = [], []
    for pt in parts:
        for f, d, it in zip(pt.get("form", []), pt.get("filingDate", []), pt.get("items", [""] * len(pt.get("form", [])))):
            d = pd.Timestamp(d)
            if f in MA and last - pd.Timedelta(days=400) <= d <= last + pd.Timedelta(days=10): fs.append(d)
            if f == "8-K" and "1.01" in [x.strip() for x in (it or "").split(",")]: k8.append(d)
    if not fs: continue
    first = min(fs)
    pre = [d for d in k8 if first - pd.Timedelta(days=45) <= d <= first]
    ann["D:" + r.code] = min([first] + pre)
A = pd.Series(ann, name="ann").rename_axis("t").reset_index()
A.to_csv(os.path.join(OUT, "announcements.csv"), index=False)
print("acquired (completed) targets:", len(A))

# ---------- A. 사건 연구 ----------
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
def lpx(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    return np.log(pd.read_parquet(p)["Close"].groupby(level=0).last().reindex(cal).values) if os.path.exists(p) else None
ev = []
for r in A.itertuples():
    lc = lpx(r.t)
    if lc is None: continue
    pos = cal.searchsorted(r.ann)
    def car(a, b):
        s, e = pos + a - 1, pos + b
        if s < 0 or e >= len(cal) or not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
        return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
    ev.append({"t": r.t, "ann": r.ann, "car_m1_p1": car(-1, 1), "car_m20_m2": car(-20, -2)})
EV = pd.DataFrame(ev); EV.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
evs = {"n": int(EV["car_m1_p1"].notna().sum()), "mean": EV["car_m1_p1"].mean(), "median": EV["car_m1_p1"].median(),
       "share_pos": (EV["car_m1_p1"] > 0).mean(), "pre_mean": EV["car_m20_m2"].mean(), "pre_median": EV["car_m20_m2"].median()}
print("event study:", {k: round(v, 4) for k, v in evs.items()})

# ---------- B. 표본·특징 ----------
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"])
pn = pn[pn["date"] <= "2024-10-01"].copy()
annd = dict(zip(A["t"], A["ann"]))
pn["y"] = [int(t in annd and d < annd[t] <= d + pd.Timedelta(days=365)) for t, d in zip(pn["t"], pn["date"])]
pn = pn[~pn.apply(lambda r: r.t in annd and annd[r.t] <= r.date, axis=1)]          # 이미 발표된 뒤는 제외
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
now2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"])); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
def sic(t):
    c = d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
    if c is None or c != c: return None
    p = os.path.join(CF, f"{int(c)}_sub.json")
    try: return str(json.load(open(p)).get("sic") or "")[:2] or None
    except Exception: return None
SIC = {t: sic(t) for t in pn["t"].unique()}; pn["sic2"] = pn["t"].map(SIC)
# 재무: 현금·부채·자산 (최초 공시 값)
src = open(os.path.join(ROOT, "task5", "05_build_rdcf_D.py")).read().split("# ---------- 시장 입력 ----------")[0]
g = {"__file__": os.path.join(ROOT, "task5", "05_build_rdcf_D.py")}; exec(src, g)
inst, first_ = g["inst"], g["first"]
cik_of = lambda t: d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
xc, xl = [], []
for t, d in zip(pn["t"], pn["date"]):
    c = cik_of(t)
    if c is None or c != c: xc.append(np.nan); xl.append(np.nan); continue
    c = int(c); a = inst(c, "Assets", d)
    cash = inst(c, "CashAndCashEquivalentsAtCarryingValue", d); debt = first_(inst(c, "LongTermDebtNoncurrent", d), inst(c, "LongTermDebt", d))
    xc.append(cash / a if a and a == a and cash == cash else np.nan); xl.append(debt / a if a and a == a and debt == debt else np.nan)
pn["x_cash"], pn["x_lev"] = xc, xl
# 직전 1년 시장 대비 수익
pn["x_ret"] = np.nan
for t, gg in pn.groupby("t"):
    lc = lpx(t)
    if lc is None: continue
    for i, d in zip(gg.index, gg["date"]):
        e = cal.searchsorted(d) - 1; s = e - 252
        if s >= 0 and np.isfinite(lc[s]) and np.isfinite(lc[e]):
            pn.at[i, "x_ret"] = (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
pn["x_size"] = np.log(pn["mcap"].where(pn["mcap"] > 0))
pn["x_ey"], pn["x_fcfy"], pn["x_ag"] = pn["EY"], pn["FCFY"], pn["AG"]
# 업종 피인수 비율: 같은 SIC2, 직전 24개월 안 발표 / 그 업종 표본 회사 수
firms = pn.groupby("sic2")["t"].nunique()
ann_sic = pd.DataFrame({"sic2": [SIC.get(t) for t in A["t"]], "ann": A["ann"]}).dropna()
pn["x_ind"] = [((ann_sic["sic2"] == s) & (ann_sic["ann"] < d) & (ann_sic["ann"] >= d - pd.Timedelta(days=730))).sum() / firms.get(s, np.nan)
               if s is not None else np.nan for s, d in zip(pn["sic2"], pn["date"])]
X = ["x_size", "x_ind", "x_ret", "x_ey", "x_fcfy", "x_cash", "x_lev", "x_ag"]
dz = pn[pn["cell"] == "설계"] if "cell" in pn else None
# 4칸 (과제 5와 같은 배정)
import hashlib
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
pn["grp"] = [("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") if t.startswith("D:") else grp.get(t) for t in pn["t"]]
pn = pn[pn["grp"].notna()]
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
pn["cell"] = [names[(g_, y % 2)] for g_, y in zip(pn["grp"], pn["date"].dt.year)]
dz = pn[pn["cell"] == "설계"]
for c in ("x_ey", "x_fcfy", "x_ag", "x_ret"):
    lo, hi = dz[c].quantile([0.01, 0.99]); pn[c] = pn[c].clip(lo, hi)
dz = pn[pn["cell"] == "설계"]
med = dz[X].median()
for c in X:
    pn[f"m_{c}"] = pn[c].isna().astype(float); pn[c] = pn[c].fillna(med[c])
B1F = ["x_size", "x_ind", "m_x_size", "m_x_ind"]; MF = X + [f"m_{c}" for c in X]
dz = pn[pn["cell"] == "설계"]
def fit(cols):
    cols = [c for c in cols if dz[c].std() > 0]
    m = sm.Logit(dz["y"], sm.add_constant(dz[cols])).fit(disp=0)
    return m, cols
mB1, cB1 = fit(B1F); mM, cM = fit(MF)
pn["pB1"] = mB1.predict(sm.add_constant(pn[cB1], has_constant="add")); pn["pM"] = mM.predict(sm.add_constant(pn[cM], has_constant="add"))
json.dump({"B1": mB1.params.to_dict(), "M": mM.params.to_dict(), "base_rate_design": float(dz["y"].mean())},
          open(os.path.join(OUT, "models.json"), "w"), indent=1, ensure_ascii=False)

def top10(df, col):
    k = df[col] >= df.groupby("date")[col].transform(lambda x: x.quantile(0.9))
    return df.loc[k, "y"].mean()

rng = np.random.default_rng(20261025)
def boot(df, fn, B=2000):
    dates = df["date"].unique(); by = {d: g for d, g in df.groupby("date")}
    vals = []
    for _ in range(B):
        s = pd.concat([by[d] for d in rng.choice(dates, len(dates))])
        try: vals.append(fn(s))
        except ValueError: pass
    return np.array(vals)

rows, logs = [], []
today = datetime.date.today().isoformat()
T = {"B1_auc": (lambda d: roc_auc_score(d["y"], d["pB1"]), 0.5),
     "B1_lift10": (lambda d: top10(d, "pB1") / d["y"].mean(), 1.0),
     "M_minus_B1_auc": (lambda d: roc_auc_score(d["y"], d["pM"]) - roc_auc_score(d["y"], d["pB1"]), 0.0),
     "M_minus_B1_top10": (lambda d: top10(d, "pM") - top10(d, "pB1"), 0.0)}
for name, (fn, null) in T.items():
    res = {}
    for c in ("설계", "확인1", "확인2", "최종"):
        if c == "최종" and not all(res[x]["p1"] < 0.05 and res[x]["est"] > null for x in ("확인1", "확인2")): break
        sub = pn[pn["cell"] == c]
        est = fn(sub); bs = boot(sub, fn)
        res[c] = {"est": est, "p1": float((bs <= null).mean()), "n": len(sub), "events": int(sub["y"].sum()), "base": sub["y"].mean()}
    for c, r in res.items():
        rows.append({"test": name, "cell": c, **r})
        logs.append([f"T7-{name}-{c}", today, 7, "피인수 12개월 예측", "MA", name, "acquired12m", c, r["n"], name,
                     round(r["est"], 5), round(null, 3), "", round(r["p1"], 4), f"events={r['events']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)
pn.to_csv(os.path.join(DATA, "task7_panel.csv"), index=False)
json.dump(evs, open(os.path.join(OUT, "event_summary.json"), "w"), indent=1)
pd.set_option("display.width", 200, "display.float_format", "{:.4f}".format)
print(res.to_string(index=False)); print("B1:", mB1.params.round(3).to_dict()); print("M:", mM.params.round(3).to_dict())
