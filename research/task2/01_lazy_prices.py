"""과제 2-01: 10-K 문장 변화 → 이후 3·6·12개월 초과수익 (PLAN.md 규칙 그대로)."""
import os, json, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "task2", "out")
os.makedirs(OUT, exist_ok=True)

f = pd.read_parquet(os.path.join(DATA, "raw", "r2", "sec__tenk_features.parquet"))
f = f[f["form"] == "10-K"].copy()
f["filed"] = pd.to_datetime(f["filed"])
f = f.sort_values(["ticker", "filed"]).drop_duplicates(["ticker", "filed"], keep="first")
prev_unc = f.set_index("acc")["md_unc"]
f["unc_d"] = f["md_unc"] - f["prev_acc"].map(prev_unc)
f = f[f["prev_acc"].notna()].reset_index(drop=True)
f = f.rename(columns={"ticker": "t"})

# --- 직전 365일 분포 기준 백분위 ---
f = f.sort_values("filed").reset_index(drop=True)
fd = f["filed"].values
for col in ["sim_full", "sim_rf", "sim_md", "rf_new", "unc_d"]:
    v = f[col].values
    pct = np.full(len(f), np.nan)
    for i in range(len(f)):
        if np.isnan(v[i]):
            continue
        lo = np.searchsorted(fd, fd[i] - np.timedelta64(365, "D"), side="left")
        hi = np.searchsorted(fd, fd[i], side="left")          # 접수일 이전만
        w = v[lo:hi]; w = w[~np.isnan(w)]
        if len(w) >= 200:
            pct[i] = (w < v[i]).mean()
    f[f"p_{col}"] = pct

def flag(p, low):
    return np.where(np.isnan(p), np.nan, ((p <= 0.2) if low else (p >= 0.8)).astype(float))

f["s_full_chg"], f["s_full_same"] = flag(f.p_sim_full, True), flag(f.p_sim_full, False)
f["s_rf_chg"], f["s_rf_same"] = flag(f.p_sim_rf, True), flag(f.p_sim_rf, False)
f["s_md_chg"], f["s_md_same"] = flag(f.p_sim_md, True), flag(f.p_sim_md, False)
f["s_rfnew"] = flag(f.p_rf_new, False)
f["s_unc_up"] = flag(f.p_unc_d, False)
SIGS = ["s_full_chg", "s_full_same", "s_rf_chg", "s_rf_same", "s_md_chg", "s_md_same", "s_rfnew", "s_unc_up"]
NEG = {"s_full_chg", "s_rf_chg", "s_md_chg", "s_rfnew", "s_unc_up"}

# --- 가격·목표 ---
spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))["Close"]
cal = spy.index; ls = np.log(spy.values)
ma200 = spy.rolling(200).mean().values
H = (63, 126, 252)
f["_pos"] = cal.searchsorted(f["filed"].values, side="right")   # 접수일 다음 거래일
for h in H:
    f[f"y_{h}"] = np.nan; f[f"raw_{h}"] = np.nan; f[f"cross_{h}"] = False
f["regime"] = None
for t, g in f.groupby("t"):
    p = os.path.join(DATA, "prices", f"{t}.parquet")
    if not os.path.exists(p):
        continue
    lc = np.log(pd.read_parquet(p)["Close"].reindex(cal).values)
    for pos, i in zip(g["_pos"].values, g.index.values):
        if pos >= len(cal) or np.isnan(lc[pos]):
            continue
        if pos > 0 and not np.isnan(ma200[pos - 1]):
            f.at[i, "regime"] = "up" if spy.values[pos - 1] > ma200[pos - 1] else "down"
        for h in H:
            e = pos + h
            if e >= len(cal) or np.isnan(lc[e]):
                continue
            r = np.exp(lc[e] - lc[pos]) - 1
            f.at[i, f"raw_{h}"] = r
            f.at[i, f"y_{h}"] = r - (np.exp(ls[e] - ls[pos]) - 1)
            f.at[i, f"cross_{h}"] = cal[e].year != cal[pos].year

f["entry"] = pd.Series(cal[np.minimum(f["_pos"].values, len(cal) - 1)])
f.loc[f["_pos"] >= len(cal), "entry"] = pd.NaT
f["month"] = f["entry"].dt.strftime("%Y-%m")
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")).set_index("t")["grp"]
f["grp"] = f["t"].map(grp)
par = np.where(f["entry"].dt.year % 2 == 1, "odd", "even")
names = {("A", "odd"): "설계", ("A", "even"): "확인1", ("B", "odd"): "확인2", ("B", "even"): "최종"}
f["cell"] = [names.get((g_, p_)) if isinstance(g_, str) else None for g_, p_ in zip(f["grp"], par)]
f["era"] = pd.cut(f["entry"].dt.year, [2000, 2012, 2018, 2030], labels=["2007-12", "2013-18", "2019~"]).astype(str)
uni = pd.read_csv(os.path.join(DATA, "universe.csv"))
f["sp500"] = f["t"].map(uni.set_index("t")["idx"].fillna("").str.contains("S&P500"))


def test(df, sig, h, neg):
    d = df.dropna(subset=[sig, f"y_{h}", "month"]).copy()
    if h == 63:
        d = d[~d[f"cross_{h}"].astype(bool)]
    d["y"], d["S"] = d[f"y_{h}"], d[sig]
    if d["S"].nunique() < 2 or len(d) < 100:
        return None
    m = smf.ols("y ~ S", d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["month"])[0]})
    D, t = m.params["S"], m.tvalues["S"]
    on = d[d.S == 1]
    net = on[f"raw_{h}"].mean() - 0.001
    if neg:
        D, t, net = -D, -t, -on[f"raw_{h}"].mean() - 0.001
    return {"n": len(d), "n_on": len(on), "D": D, "p1": 1 - norm.cdf(t),
            "y_on": on["y"].mean(), "y_off": d.loc[d.S == 0, "y"].mean(), "raw_on_net": net}


rows, logs = [], []
today = datetime.date.today().isoformat()
for sig in SIGS:
    ng = sig in NEG
    for h in H:
        res = {"설계": test(f[f.cell == "설계"], sig, h, ng)}
        if res["설계"] and res["설계"]["D"] > 0:
            for c in ["확인1", "확인2"]:
                res[c] = test(f[f.cell == c], sig, h, ng)
            ok = res["설계"]["raw_on_net"] > 0 and all(
                res[c] and res[c]["D"] > 0 and res[c]["p1"] < 0.05 and res[c]["raw_on_net"] > 0 for c in ["확인1", "확인2"])
            if ok:
                res["최종"] = test(f[f.cell == "최종"], sig, h, ng)
        for c, r in res.items():
            if r is None:
                continue
            rows.append({"signal": sig, "dir": "-" if ng else "+", "h": h, "cell": c, **r})
            logs.append([f"T2-{sig}-{h}-{c}", today, 2, "10-K 변화 → 이후 초과수익", "LazyPrices", sig, f"Y_{h}", c,
                         r["n"], "D(부호 뒤집음)" if ng else "D", round(r["D"], 5), "", "", round(r["p1"], 4),
                         f"n_on={r['n_on']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs:
        fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)

ref = []
dz = f[f.cell == "설계"]
for sig in SIGS:
    for h in H:
        for col in ["regime", "era", "sp500"]:
            for v, sub in dz.groupby(col):
                r = test(sub, sig, h, False)
                if r:
                    ref.append({"signal": sig, "h": h, "split": col, "value": str(v), "n_on": r["n_on"], "D": r["D"]})
pd.DataFrame(ref).to_csv(os.path.join(OUT, "design_splits.csv"), index=False)
meta = {"events": int(len(f)), "tickers": int(f.t.nunique()), "with_y252": int(f.y_252.notna().sum()),
        "cells": f.cell.value_counts().to_dict(), "first": str(f.filed.min().date()), "last": str(f.filed.max().date())}
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=1)

pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(meta)
print(res.to_string(index=False))
print("\n설계 칸 분할 참고 (원래 부호 D)")
print(pd.DataFrame(ref).pivot_table(index=["signal", "h"], columns=["split", "value"], values="D").to_string())
# 설계 칸 sim_full 5분위별 평균 초과수익 (참고)
q = dz.dropna(subset=["p_sim_full"]).copy(); q["q"] = pd.cut(q.p_sim_full, [-.01, .2, .4, .6, .8, 1.01], labels=False)
print("\n설계 칸 sim_full 백분위 5구간별 평균 초과수익 (0 = 가장 많이 바꿈)")
print(q.groupby("q")[["y_63", "y_126", "y_252"]].mean().to_string())
