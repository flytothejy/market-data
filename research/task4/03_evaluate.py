"""과제 4-03: 13F 따라 사기 평가 (PLAN.md §3·§4 그대로)."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "f13"); PX = os.path.join(ROOT, "data", "prices"); OUT = os.path.join(ROOT, "task4", "out")
os.makedirs(OUT, exist_ok=True)
h = pd.read_parquet(os.path.join(RAW, "holdings_hist.parquet"))
h = h[(h["sh_type"] == "SH") & (h["put_call"].fillna("") == "")].copy()
h["cusip"] = h["cusip"].str.upper().str.zfill(9)
c2t = pd.read_csv(os.path.join(RAW, "cusip_ticker.csv"), dtype=str).set_index("cusip")["ticker"]
h["t"] = h["cusip"].map(c2t).str.replace("/", "-").str.replace(" ", "-").str.replace(".", "-")
h = h.groupby(["manager_cik", "period", "filed", "cusip", "t"], dropna=False).agg(value=("value", "sum"), shares=("shares", "sum")).reset_index()
h["period"] = pd.to_datetime(h["period"]); h["filed"] = pd.to_datetime(h["filed"])
h = h[h["period"] <= "2026-03-31"]

spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index
pc = {}
def fwd(t, d, n):
    if not isinstance(t, str): return np.nan
    if t not in pc:
        p = os.path.join(PX, f"{t}.parquet"); pc[t] = pd.read_parquet(p)["Close"].reindex(cal) if os.path.exists(p) else None
    s = pc[t]
    if s is None: return np.nan
    i = cal.searchsorted(d, side="right")              # 공개일 다음 거래일
    if i + n >= len(cal): return np.nan
    a, b = s.iloc[i], s.iloc[i + n]
    return b / a - 1 if a == a and b == b and a > 0 else np.nan
def spyfwd(d, n):
    i = cal.searchsorted(d, side="right")
    return spy.iloc[i + n] / spy.iloc[i] - 1 if i + n < len(cal) else np.nan

# ---------- 신호 ----------
recs = []
for cik, g in h.groupby("manager_cik"):
    pers = sorted(g["period"].unique())
    for k, per in enumerate(pers):
        cur = g[g["period"] == per]; filed = cur["filed"].iloc[0]
        tot = cur["value"].sum()
        top = set(cur.sort_values("value", ascending=False)["cusip"].head(10))
        prev = g[g["period"] == pers[k - 1]] if k > 0 and (per - pers[k - 1]).days < 120 else None
        for r in cur.itertuples():
            new = prev is not None and r.cusip not in set(prev["cusip"])
            add = False
            if prev is not None and not new:
                ps = prev.loc[prev["cusip"] == r.cusip, "shares"].sum()
                add = ps > 0 and r.shares >= 1.5 * ps
            recs.append({"cik": cik, "period": per, "filed": filed, "cusip": r.cusip, "t": r.t, "w": r.value / tot if tot else np.nan,
                         "N": int(new), "A": int(add), "T": int(r.cusip in top), "has_prev": prev is not None})
s = pd.DataFrame(recs)
for n in (63, 252):
    s[f"r{n}"] = [fwd(t, d, n) for t, d in zip(s["t"], s["filed"])]
    sp = {d: spyfwd(d, n) for d in s["filed"].unique()}
    s[f"s{n}"] = s["filed"].map(sp)
s["fyear"] = s["filed"].dt.year
rng = np.random.default_rng(20261024)
mg = sorted(s["cik"].unique()); rng.shuffle(mg)
grp = {c: ("A" if i % 2 == 0 else "B") for i, c in enumerate(mg)}
s["grp"] = s["cik"].map(grp); s["parity"] = np.where(s["fyear"] % 2 == 1, "odd", "even")
CELLS = {"설계": ("A", "odd"), "확인1": ("A", "even"), "확인2": ("B", "odd"), "최종": ("B", "even")}
s.to_csv(os.path.join(ROOT, "data", "task4_signals.csv"), index=False)
print("rows", len(s), "price coverage r63", s["r63"].notna().mean().round(3), "managers", s["cik"].nunique())


def units(df, test, n):
    """(운용사,분기) 단위 값: y = 신호 평균 수익 − 비교 대상, raw = 신호 평균 원수익."""
    out = []
    if test == "C_spy":
        nb = df[df["N"] == 1].dropna(subset=[f"r{n}"])
        for per, g in nb.groupby("period"):
            cnt = g.groupby("cusip")["cik"].nunique(); cs = set(cnt[cnt >= 2].index)
            if not cs: continue
            gg = g[g["cusip"].isin(cs)].sort_values("filed")
            # 둘째 공개일 다음 날 진입
            ent = gg.groupby("cusip").apply(lambda x: x["filed"].iloc[1], include_groups=False)
            r = [fwd(gg.loc[gg.cusip == c, "t"].iloc[0], d, n) for c, d in ent.items()]
            sp = [spyfwd(d, n) for d in ent.values]
            r, sp = np.array(r, float), np.array(sp, float); ok = ~np.isnan(r)
            if ok.any():
                out.append({"period": per, "y": np.mean(r[ok] - sp[ok]), "raw": np.mean(r[ok])})
        return pd.DataFrame(out)
    sig = {"N_spy": "N", "N_old": "N", "A_spy": "A", "T_spy": "T"}[test]
    for (cik, per), g in df.groupby(["cik", "period"]):
        if sig in ("N", "A") and not g["has_prev"].iloc[0]: continue
        on = g[(g[sig] == 1)].dropna(subset=[f"r{n}"])
        if on.empty: continue
        if test == "N_old":
            old = g[(g["N"] == 0) & (g["A"] == 0)].dropna(subset=[f"r{n}"])
            if old.empty: continue
            y = on[f"r{n}"].mean() - old[f"r{n}"].mean()
        else:
            y = (on[f"r{n}"] - on[f"s{n}"]).mean()
        out.append({"period": per, "y": y, "raw": on[f"r{n}"].mean()})
    return pd.DataFrame(out)


def test(df, tst, n):
    u = units(df, tst, n)
    if len(u) < 5: return None
    m = smf.ols("y ~ 1", u).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(u["period"])[0]})
    return {"units": len(u), "D": m.params.iloc[0], "p1": 1 - norm.cdf(m.tvalues.iloc[0]), "net": u["raw"].mean() - 0.001}


rows, logs = [], []
today = datetime.date.today().isoformat()
for tst in ["N_spy", "N_old", "A_spy", "T_spy", "C_spy"]:
    for n in (63, 252):
        res = {}
        for c, (g_, p_) in CELLS.items():
            if c != "설계" and not (res.get("설계") and res["설계"]["D"] > 0): break
            if c == "최종" and not (res["설계"]["net"] > 0 and all(res.get(x) and res[x]["D"] > 0 and res[x]["p1"] < 0.05 and res[x]["net"] > 0 for x in ("확인1", "확인2"))): break
            r = test(s[(s["grp"] == g_) & (s["parity"] == p_)], tst, n)
            if r is None: break
            res[c] = r
        for c, r in res.items():
            rows.append({"test": tst, "h": n, "cell": c, **r})
            logs.append([f"T4-{tst}-{n}-{c}", today, 4, "13F 공개 후 따라 사기", "13F", tst, f"ab{n}", c, r["units"], "D",
                         round(r["D"], 5), "", "", round(r["p1"], 4), f"net={round(r['net'], 4)}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)

# 참고: 전체·운용사별·시기별 (칸 무시)
ref = []
s["era"] = pd.cut(s["fyear"], [2012, 2017, 2021, 2030], labels=["2013-17", "2018-21", "2022~"]).astype(str)
for tst in ["N_spy", "N_old", "T_spy"]:
    for n in (63, 252):
        u = units(s, tst, n); ref.append({"test": tst, "h": n, "split": "all", "value": "all", "D": u["y"].mean(), "units": len(u)})
        for e, sub in s.groupby("era"):
            u = units(sub, tst, n); ref.append({"test": tst, "h": n, "split": "era", "value": e, "D": u["y"].mean(), "units": len(u)})
pm = []
for cik, sub in s.groupby("cik"):
    u = units(sub, "N_spy", 63)
    if len(u) >= 8: pm.append({"cik": cik, "units": len(u), "D": u["y"].mean()})
pm = pd.DataFrame(pm); pm.to_csv(os.path.join(OUT, "per_manager_N63.csv"), index=False)
pd.DataFrame(ref).to_csv(os.path.join(OUT, "reference.csv"), index=False)
pd.set_option("display.width", 250, "display.float_format", "{:.4f}".format)
print(res.to_string(index=False)); print(pd.DataFrame(ref).to_string(index=False))
print("운용사별 N_spy 63일: 양수", int((pm.D > 0).sum()), "/", len(pm), "중앙값", round(pm.D.median(), 4))
