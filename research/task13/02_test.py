"""과제 2-8-02: 사전 등록 검정 (PLAN.md §5). 모든 신호의 가설 방향은 음(−) → 부호를 뒤집은 D로 판정."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "task13", "out")
X = pd.read_parquet(os.path.join(OUT, "panel.parquet"))
X["q"] = X["fday"].dt.to_period("Q")
lo = X.groupby("q")["y3"].transform(lambda s: s.quantile(0.01))
hi = X.groupby("q")["y3"].transform(lambda s: s.quantile(0.99))
X["y3w"] = X["y3"].clip(lo, hi)
X["y1"] = X["beat"] - X["b2"]
SIGS = ["AR", "INV", "DEBT", "COMP2"]
TG = {"Y1": ("y1", "rday"), "Y2": ("y2", "rday"), "Y3": ("y3w", "fday")}


def test(df, sig, tg):
    yc, cc = TG[tg]
    d = df.dropna(subset=[sig, yc]).copy()
    if d[sig].nunique() < 2 or len(d) < 50:
        return None
    d["y"], d["S"] = d[yc], d[sig]
    m = smf.ols("y ~ S", data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cc])[0]})
    D, t = -m.params["S"], -m.tvalues["S"]          # 가설 방향 음수 → 뒤집음
    on = d[d["S"] == 1]
    r = {"n": len(d), "n_on": len(on), "share_on": len(on) / len(d), "D": D, "t": t, "p1": 1 - norm.cdf(t),
         "mean_on": on["y"].mean(), "mean_off": d.loc[d["S"] == 0, "y"].mean()}
    if tg == "Y3":
        r["short_net"] = -on["ret3"].mean() - 0.001
    return r


rows, logs = [], []
today = datetime.date.today().isoformat()
for sig in SIGS:
    for tg in TG:
        res = {"설계": test(X[X["cell"] == "설계"], sig, tg)}
        if res["설계"] and res["설계"]["D"] > 0:
            for c in ["확인1", "확인2"]:
                res[c] = test(X[X["cell"] == c], sig, tg)
            ok = all(res[c] and res[c]["D"] > 0 and res[c]["p1"] < 0.05 for c in ["확인1", "확인2"])
            if tg == "Y3":
                ok = ok and all(res[c]["short_net"] > 0 for c in ["설계", "확인1", "확인2"])
            if ok:
                res["최종"] = test(X[X["cell"] == "최종"], sig, tg)
        for c, r in res.items():
            if r is None:
                continue
            rows.append({"signal": sig, "target": tg, "cell": c, **r})
            logs.append([f"T13-{sig}-{tg}-{c}", today, "2-8", "체질 경고가 다음 분기 결과를 가르나(생존자)", sig, "flag", tg, c,
                         r["n"], "D(부호 뒤집음)", round(r["D"], 5), "", "", round(r["p1"], 4), f"n_on={r['n_on']}"])
R = pd.DataFrame(rows)
R.to_csv(os.path.join(OUT, "results.csv"), index=False)
with open(os.path.join(ROOT, "log.csv"), "a") as f:
    for l in logs:
        f.write(",".join(str(x) for x in l) + "\n")

# 참고: 설계 칸 국면·시기별
ref = []
dz = X[X["cell"] == "설계"]
for sig in SIGS:
    for tg in TG:
        for col in ["regime", "era"]:
            for v, sub in dz.groupby(col, observed=True):
                r = test(sub, sig, tg)
                if r:
                    ref.append({"signal": sig, "target": tg, "split": col, "value": v, "n": r["n"], "D": r["D"], "p1": r["p1"]})
pd.DataFrame(ref).to_csv(os.path.join(OUT, "design_splits.csv"), index=False)
pd.set_option("display.width", 200)
print(R[["signal", "target", "cell", "n", "n_on", "D", "t", "p1", "mean_on", "mean_off"] + (["short_net"] if "short_net" in R else [])].round(4).to_string(index=False))
