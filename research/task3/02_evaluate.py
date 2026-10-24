"""과제 3-02: 편입 예측 평가 (PLAN.md §3·§4 규칙 그대로)."""
import os, datetime
import numpy as np, pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); OUT = os.path.join(ROOT, "task3", "out")
pn = pd.read_csv(os.path.join(DATA, "task3_panel.csv"), parse_dates=["date"])
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")).set_index("t")["grp"]
pn["grp"] = pn["t"].map(lambda t: grp.get(t, grp.get(t.replace("-", "."))))
pn = pn[pn["mcap"].notna() & pn["grp"].notna()].copy()
pn["parity"] = np.where(pn["date"].dt.year % 2 == 1, "odd", "even")
CELLS = {"설계": ("A", "odd"), "확인1": ("A", "even"), "확인2": ("B", "odd"), "최종": ("B", "even")}
LISTS = {"P1": lambda d: d, "P2": lambda d: d[d["earn_ok"] == 1], "P3": lambda d: d[(d["earn_ok"] == 1) & (d["liq_ok"] == 1)]}


def per_date(df, lst, k, target="add3"):
    out = []
    for d, g in df.groupby("date"):
        g = g.sort_values("mcap", ascending=False)
        top = LISTS[lst](g).head(k)
        b = g.head(25)
        if len(top) == 0:
            continue
        out.append({"date": d, "hit": top[target].mean(), "b25": b[target].mean(), "b0": g[target].mean(),
                    "n_hits": int(top[target].sum()), "n_add": int(g[target].sum())})
    return pd.DataFrame(out)


def ttest(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan, np.nan
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return t, 1 - stats.t.cdf(t, len(x) - 1)


rows, logs = [], []
today = datetime.date.today().isoformat()
for lst in LISTS:
    for k in (5, 10, 20):
        res = {}
        for c, (g_, p_) in CELLS.items():
            if c != "설계" and not (res.get("설계") and res["설계"]["D"] > 0):
                break
            if c == "최종" and not all(res.get(x) and res[x]["D"] > 0 and res[x]["p1"] < 0.05 for x in ("확인1", "확인2")):
                break
            sub = pn[(pn["grp"] == g_) & (pn["parity"] == p_)]
            pdd = per_date(sub, lst, k)
            D = (pdd["hit"] - pdd["b25"])
            t, p = ttest(D)
            res[c] = {"dates": len(pdd), "hit": pdd["hit"].mean(), "b25": pdd["b25"].mean(), "b0": pdd["b0"].mean(),
                      "D": D.mean(), "p1": p, "hits": int(pdd["n_hits"].sum()), "adds_in_cell": int(pdd["n_add"].sum())}
        for c, r in res.items():
            rows.append({"list": lst, "k": k, "cell": c, **r})
            logs.append([f"T3-{lst}-k{k}-{c}", today, 3, "편입 후보 적중률 vs 상위25 기준선", "SP500add", f"{lst}_k{k}",
                         "add3", c, r["dates"], "D", round(r["D"], 5), round(r["b25"], 5), "", round(r["p1"], 4) if r["p1"] == r["p1"] else "",
                         f"hits={r['hits']}"])

# 수익률: P3, K=10
rres = {}
for c, (g_, p_) in CELLS.items():
    if c != "설계" and not (rres.get("설계") and rres["설계"]["D"] > 0):
        break
    if c == "최종" and not all(rres.get(x) and rres[x]["D"] > 0 and rres[x]["p1"] < 0.05 and rres[x]["net"] > 0 for x in ("확인1", "확인2")):
        break
    sub = pn[(pn["grp"] == g_) & (pn["parity"] == p_)]
    rr = []
    for d, g in sub.groupby("date"):
        g = g.sort_values("mcap", ascending=False)
        top = LISTS["P3"](g).head(10)
        oth = g.head(25)[~g.head(25)["t"].isin(top["t"])]
        if len(top) and len(oth):
            rr.append({"top": top["ab3"].mean(), "oth": oth["ab3"].mean(), "raw": top["raw3"].mean()})
    rr = pd.DataFrame(rr); D = rr["top"] - rr["oth"]; t, p = ttest(D)
    rres[c] = {"dates": len(rr), "top_ab": rr["top"].mean(), "oth_ab": rr["oth"].mean(), "D": D.mean(), "p1": p,
               "net": rr["raw"].mean() - 0.001}
for c, r in rres.items():
    rows.append({"list": "P3_ret", "k": 10, "cell": c, **r})
    logs.append([f"T3-ret-P3k10-{c}", today, 3, "편입 후보 보유 초과수익 vs 상위25 나머지", "SP500add", "P3_k10", "ab3", c,
                 r["dates"], "D", round(r["D"], 5), "", "", round(r["p1"], 4), f"net={round(r['net'], 4)}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs:
        fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)

# 참고: 전체(칸 무시) 요약, 12개월 편입 적중률
ref = []
for lst in LISTS:
    for k in (10, 20, 40):
        a = per_date(pn, lst, k); b = per_date(pn, lst, k, "add12")
        ref.append({"list": lst, "k_full": k, "hit3": a["hit"].mean(), "b50_3": per_date(pn, "P1", 50)["hit"].mean(),
                    "b0_3": a["b0"].mean(), "hit12": b["hit"].mean(), "b0_12": b["b0"].mean()})
pd.DataFrame(ref).to_csv(os.path.join(OUT, "overall_ref.csv"), index=False)
pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(res.to_string(index=False)); print("\n전체 참고"); print(pd.DataFrame(ref).to_string(index=False))
