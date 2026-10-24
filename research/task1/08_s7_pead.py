"""과제 1-08: S7 실적 발표 후 표류(PEAD) 검정 — PLAN.md §7 규칙 그대로."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm
from common import load_events, ROOT, OUT, DATA

ev = load_events()
ev = ev[ev["rday"].notna() & ev["abret"].notna()].reset_index(drop=True)
spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))["Close"]
cal = spy.index; ls = np.log(spy.values)
ev["_pos"] = cal.searchsorted(ev["rday"].values)
H = (20, 60)
car = {h: np.full(len(ev), np.nan) for h in H}
raw = {h: np.full(len(ev), np.nan) for h in H}
cross = {h: np.zeros(len(ev), bool) for h in H}
for t, g in ev.groupby("t"):
    lc = np.log(pd.read_parquet(os.path.join(DATA, "prices", f"{t}.parquet"))["Close"].reindex(cal).values)
    for pos, i in zip(g["_pos"].values, g.index.values):
        for h in H:
            e = pos + h
            if e >= len(cal) or np.isnan(lc[pos]) or np.isnan(lc[e]):
                continue
            r = np.exp(lc[e] - lc[pos]) - 1
            raw[h][i] = r
            car[h][i] = r - (np.exp(ls[e] - ls[pos]) - 1)
            cross[h][i] = cal[e].year != cal[pos].year
for h in H:
    ev[f"y4_{h}"], ev[f"raw_{h}"], ev[f"cross_{h}"] = car[h], raw[h], cross[h]
ev["month"] = ev["rday"].dt.strftime("%Y-%m")

dz = ev[ev["cell"] == "설계"]
for name, col in [("surp", "surp"), ("ear", "abret")]:
    lo, hi = dz[col].quantile([0.2, 0.8])
    x = ev[col]
    ev[f"s7_{name}_top"] = np.where(x.notna(), (x >= hi).astype(float), np.nan)
    ev[f"s7_{name}_bot"] = np.where(x.notna(), (x <= lo).astype(float), np.nan)
    print(name, "cutoffs", round(lo, 4), round(hi, 4))
NEG = {"s7_surp_bot", "s7_ear_bot"}


def test(df, sig, h, neg):
    d = df[~df[f"cross_{h}"]].dropna(subset=[sig, f"y4_{h}"]).copy()
    d["y"], d["S"] = d[f"y4_{h}"], d[sig]
    m = smf.ols("y ~ S", d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["month"])[0]})
    D, t = m.params["S"], m.tvalues["S"]
    on = d[d.S == 1]
    net = on[f"raw_{h}"].mean() - 0.001
    if neg:
        D, t, net = -D, -t, -on[f"raw_{h}"].mean() - 0.001
    return {"n": len(d), "n_on": len(on), "D": D, "p1": 1 - norm.cdf(t), "car_on": on["y"].mean(),
            "car_off": d.loc[d.S == 0, "y"].mean(), "raw_on_net": net}


rows, logs = [], []
today = datetime.date.today().isoformat()
for sig in ["s7_surp_top", "s7_surp_bot", "s7_ear_top", "s7_ear_bot"]:
    ng = sig in NEG
    for h in H:
        res = {"설계": test(ev[ev.cell == "설계"], sig, h, ng)}
        if res["설계"]["D"] > 0:
            for c in ["확인1", "확인2"]:
                res[c] = test(ev[ev.cell == c], sig, h, ng)
            ok = all(res[c]["D"] > 0 and res[c]["p1"] < 0.05 and res[c]["raw_on_net"] > 0 for c in ["확인1", "확인2"]) \
                and res["설계"]["raw_on_net"] > 0
            if ok:
                res["최종"] = test(ev[ev.cell == "최종"], sig, h, ng)
        for c, r in res.items():
            rows.append({"signal": sig, "dir": "-" if ng else "+", "h": h, "cell": c, **r})
            logs.append([f"T1-S7-{sig}-{h}-{c}", today, 1, "PEAD: 발표 후 표류(S1~S5 뒤 추가)", "S7", sig,
                         f"Y4_{h}", c, r["n"], "D(부호 뒤집음)" if ng else "D", round(r["D"], 5), "", "",
                         round(r["p1"], 4), f"n_on={r['n_on']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as f:
    for l in logs:
        f.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "s7_results.csv"), index=False)

# 참고: 설계 칸 시기별 (원래 부호), 5분위별 평균 표류 (설계 칸)
ev["era"] = ev["era"].astype(str)
ref = []
for sig in ["s7_surp_top", "s7_surp_bot", "s7_ear_top", "s7_ear_bot"]:
    for h in H:
        for v, sub in ev[ev.cell == "설계"].groupby("era"):
            r = test(sub, sig, h, False); ref.append({"signal": sig, "h": h, "era": v, "D": r["D"]})
pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(res.to_string(index=False))
print("\n설계 칸 시기별 D (원래 부호)")
print(pd.DataFrame(ref).pivot_table(index=["signal", "h"], columns="era", values="D").to_string())
q = ev[(ev.cell == "설계") & ~ev.cross_60].dropna(subset=["surp", "y4_60"]).copy()
q["sq"] = pd.qcut(q["surp"], 5, labels=False)
print("\n설계 칸 서프라이즈 5분위별 평균 초과수익: 반응일 / +20일 / +60일")
print(q.groupby("sq")[["abret", "y4_20", "y4_60"]].mean().to_string())
