"""과제 1 공통: 이벤트 적재, 목표·기준선 만들기, 검정, 판정 절차 (04_s1_streak.py와 같은 규칙)."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "task1", "out")
DATA = os.path.join(ROOT, "data")


def load_events():
    ev = pd.read_csv(os.path.join(DATA, "events.csv"), parse_dates=["date", "rday"])
    ev = ev.sort_values(["t", "date"]).reset_index(drop=True)
    ev["cq"] = ev["date"].dt.to_period("Q")
    med = ev.groupby("cq")["surp"].transform("median")
    ev["y2"] = np.where(ev["surp"].notna(), (ev["surp"] > med).astype(float), np.nan)
    ev["y1"] = (ev["cls"] == "beat").astype(float)
    g = ev.groupby("t")
    ev["b2_y1"] = g["y1"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).mean())
    ev["b2_y2"] = g["y2"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).mean())
    ev["b1"] = ev.groupby("year")["y1"].transform("mean")
    ev["cdate"] = ev["rday"].fillna(ev["date"]).dt.strftime("%Y-%m-%d")
    ev["era"] = pd.cut(ev["year"], [1990, 2009, 2014, 2019, 2030], labels=["~2009", "2010-14", "2015-19", "2020~"])
    return ev


def test(df, sig, target):
    if target == "Y1":
        d = df.dropna(subset=[sig, "b2_y1"]).copy(); d["y"] = d["y1"] - d["b2_y1"]
    elif target == "Y2":
        d = df.dropna(subset=[sig, "y2", "b2_y2"]).copy(); d["y"] = d["y2"] - d["b2_y2"]
    else:
        d = df.dropna(subset=[sig, "abret"]).copy(); d["y"] = d["abret"]
    d["S"] = d[sig]
    if d["S"].nunique() < 2 or len(d) < 50:
        return None
    m = smf.ols("y ~ S", data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cdate"])[0]})
    D, t = m.params["S"], m.tvalues["S"]
    on = d[d["S"] == 1]
    r = {"n": len(d), "n_on": len(on), "share_on": len(on) / len(d), "D": D, "t": t, "p1": 1 - norm.cdf(t),
         "mean_on": on["y"].mean(), "mean_off": d.loc[d["S"] == 0, "y"].mean()}
    if target == "Y1":
        r["P_beat_on"] = on["y1"].mean(); r["B1_on"] = on["b1"].mean(); r["B2_on"] = on["b2_y1"].mean()
    if target == "Y3":
        r["raw_on_net"] = on["ret"].mean() - 0.001
        r["up_on"] = (on["abret"] > 0).mean(); r["up_off"] = (d.loc[d["S"] == 0, "abret"] > 0).mean()
    return r


def run(ev, sigs, sname, hyp, tag, targets=("Y1", "Y2", "Y3")):
    """PLAN §4 절차: 설계 D>0 → 확인①② (D>0 & p<0.05, Y3는 비용 후 원수익>0) → 최종 1회."""
    rows, logs = [], []
    today = datetime.date.today().isoformat()
    for sig in sigs:
        for tg in targets:
            res = {"설계": test(ev[ev["cell"] == "설계"], sig, tg)}
            if res["설계"] is not None and res["설계"]["D"] > 0:
                for c in ["확인1", "확인2"]:
                    res[c] = test(ev[ev["cell"] == c], sig, tg)
                ok = all(res[c] and res[c]["D"] > 0 and res[c]["p1"] < 0.05 for c in ["확인1", "확인2"])
                if tg == "Y3":
                    ok = ok and all(res[c]["raw_on_net"] > 0 for c in ["설계", "확인1", "확인2"])
                if ok:
                    res["최종"] = test(ev[ev["cell"] == "최종"], sig, tg)
            for c, r in res.items():
                if r is None:
                    continue
                rows.append({"signal": sig, "target": tg, "cell": c, **r})
                logs.append([f"T1-{tag}-{sig}-{tg}-{c}", today, 1, hyp, sname, sig, tg, c, r["n"], "D",
                             round(r["D"], 5), "", "", round(r["p1"], 4), f"n_on={r['n_on']}"])
    with open(os.path.join(ROOT, "log.csv"), "a") as f:
        for l in logs:
            f.write(",".join(str(x) for x in l) + "\n")
    return pd.DataFrame(rows)


def design_splits(ev, sigs, targets=("Y1", "Y2", "Y3")):
    ref = []
    dz = ev[ev["cell"] == "설계"]
    for sig in sigs:
        for tg in targets:
            for col in ["regime", "era"]:
                for v, sub in dz.groupby(col, observed=True):
                    r = test(sub, sig, tg)
                    if r:
                        ref.append({"signal": sig, "target": tg, "split": col, "value": v,
                                    "n": r["n"], "D": r["D"], "p1": r["p1"]})
    return pd.DataFrame(ref)
