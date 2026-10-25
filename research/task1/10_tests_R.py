"""과제 1-10: 재검증 1R 검정 (PLAN §8). 검정 8개 + 반응 기본 비율 비교."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); OUT = os.path.join(ROOT, "task1", "out")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean")
E = pd.read_csv(os.path.join(DATA, "events_R.csv"), parse_dates=["date", "rday"]).reset_index(drop=True)
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)

def load(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    return pd.read_parquet(p)["Close"].groupby(level=0).last().reindex(cal).values

E["_pos"] = cal.searchsorted(E["rday"].values)
for c in ("car20", "car5", "y4_20", "y4_60", "raw_20", "raw_60"): E[c] = np.nan
E["cross_20"] = False; E["cross_60"] = False
for t, g in E.groupby("t"):
    lc = np.log(load(t))
    for pos, i in zip(g["_pos"].values, g.index.values):
        e = pos - 1
        for w in (20, 5):
            s = e - w
            if s >= 0 and not np.isnan(lc[s:e + 1]).any():
                E.at[i, f"car{w}"] = (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
        if np.isnan(lc[pos]): continue
        for h in (20, 60):
            end = pos + h
            if end >= len(cal): continue
            seg = lc[pos:end + 1]; ok = np.where(~np.isnan(seg))[0]
            last = ok[-1]                                    # 상장폐지면 마지막 가격에서 현금
            r = np.exp(seg[last] - seg[0]) - 1
            E.at[i, f"raw_{h}"] = r
            E.at[i, f"y4_{h}"] = r - (np.exp(ls[end] - ls[pos]) - 1)
            E.at[i, f"cross_{h}"] = cal[end].year != cal[pos].year
E["cdate"] = E["rday"].dt.strftime("%Y-%m-%d"); E["month"] = E["rday"].dt.strftime("%Y-%m")

dz = E[E["cell"] == "설계"]
for w in (20, 5):
    lo, hi = dz[f"car{w}"].quantile([0.2, 0.8]); x = E[f"car{w}"]
    E[f"s3_{w}_top"] = np.where(x.notna(), (x >= hi).astype(float), np.nan)
    E[f"s3_{w}_bot"] = np.where(x.notna(), (x <= lo).astype(float), np.nan)
lo, hi = dz["abret"].quantile([0.2, 0.8])
E["s7_ear_top"] = (E["abret"] >= hi).astype(float); E["s7_ear_bot"] = (E["abret"] <= lo).astype(float)

def test(df, sig, y, cl, neg=False, raw=None, cross=None):
    d = df.dropna(subset=[sig, y]).copy()
    if cross: d = d[~d[cross].astype(bool)]
    d["Y"], d["S"] = d[y], d[sig]
    m = smf.ols("Y ~ S", d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cl])[0]})
    D, t = m.params["S"], m.tvalues["S"]
    on = d[d.S == 1]; net = on[raw].mean() - 0.001
    if neg: D, t, net = -D, -t, -on[raw].mean() - 0.001
    return {"n": len(d), "n_on": len(on), "D": D, "p1": 1 - norm.cdf(t), "net": net,
            "up_on": (on["Y"] > 0).mean(), "up_off": (d.loc[d.S == 0, "Y"] > 0).mean()}

TESTS = [(s, "abret", "cdate", False, "ret", None) for s in ("s3_20_top", "s3_20_bot", "s3_5_top", "s3_5_bot")] + \
        [(s, f"y4_{h}", "month", s.endswith("bot"), f"raw_{h}", f"cross_{h}") for s in ("s7_ear_top", "s7_ear_bot") for h in (20, 60)]
rows, logs = [], []
today = datetime.date.today().isoformat()
for sig, y, cl, neg, raw, cross in TESTS:
    res = {}
    for c in ("설계", "확인1", "확인2", "최종"):
        if c != "설계" and not res["설계"]["D"] > 0: break
        if c == "최종" and not (res["설계"]["net"] > 0 and all(res[x]["D"] > 0 and res[x]["p1"] < 0.05 and res[x]["net"] > 0 for x in ("확인1", "확인2"))): break
        res[c] = test(E[E["cell"] == c], sig, y, cl, neg, raw, cross)
    for c, r in res.items():
        rows.append({"signal": sig, "target": y, "dir": "-" if neg else "+", "cell": c, **r})
        logs.append([f"T1Rc-{sig}-{y}-{c}", today, 1, "생존편향 재검증(상장폐지 포함)", "1R", sig, y, c, r["n"],
                     "D(부호 뒤집음)" if neg else "D", round(r["D"], 5), "", "", round(r["p1"], 4), f"n_on={r['n_on']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "R_results.csv"), index=False)

# 기술 통계: 지금 종목만 vs 상장폐지 포함
def br(d):
    return pd.Series({"events": len(d), "ab_mean": d["abret"].mean(), "ab_up": (d["abret"] > 0).mean(), "ab_absmed": d["abret"].abs().median(),
                      "y4_60_mean": d.loc[~d["cross_60"].astype(bool), "y4_60"].mean()})
base = pd.DataFrame({"지금 종목만": br(E[E["src"] == "cur"]), "상장폐지만": br(E[E["src"] == "delisted"]), "합계": br(E)}).T
base.to_csv(os.path.join(OUT, "R_base.csv"))
# 참고: 같은 검정을 지금 종목만(같은 필터)으로 — 설계 칸 D
cmp = []
for sig, y, cl, neg, raw, cross in TESTS:
    for src, sub in (("cur", E[E["src"] == "cur"]), ("all", E)):
        r = test(sub[sub["cell"] == "설계"], sig, y, cl, False, raw, cross)
        cmp.append({"signal": sig, "target": y, "universe": src, "D_raw_sign": r["D"]})
pd.DataFrame(cmp).to_csv(os.path.join(OUT, "R_compare.csv"), index=False)
pd.set_option("display.width", 220, "display.float_format", "{:.4f}".format)
print(base.to_string()); print(res.to_string(index=False)); print(pd.DataFrame(cmp).pivot_table(index=["signal", "target"], columns="universe", values="D_raw_sign").to_string())
