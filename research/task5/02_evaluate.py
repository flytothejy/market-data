"""과제 5-02: 재무 신호 5분위 평가 (PLAN.md §3·§4 그대로)."""
import os, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); OUT = os.path.join(ROOT, "task5", "out"); os.makedirs(OUT, exist_ok=True)
import hashlib
PANEL = os.environ.get("PANEL", "task5_panel.csv")
pn = pd.read_csv(os.path.join(DATA, PANEL), parse_dates=["date"])
if os.environ.get("RETCOL") == "s":                       # 부실 상장폐지 −30% 민감도
    pn["r63"], pn["r252"] = pn["r63s"], pn["r252s"]
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv"))
grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
pn["grp"] = pn["t"].map(grp)
dk = pn["t"].str.startswith("D:")
pn.loc[dk, "grp"] = pn.loc[dk, "t"].map(lambda k: "A" if hashlib.md5(k[2:].encode()).digest()[0] % 2 == 0 else "B")
pn = pn[pn["grp"].notna()]
pn["parity"] = np.where(pn["date"].dt.year % 2 == 1, "odd", "even")
# 결과 확인 후 보완 (PLAN 변경 이력): 날짜별 수익률 상·하위 1% 윈저화, 선택적으로 시점 시가총액 하한
WINS = os.environ.get("WINS", "1") == "1"; MINCAP = float(os.environ.get("MINCAP", "0")); TAG = os.environ.get("TAG", "w")
if WINS:
    for n in (63, 252):
        lo = pn.groupby("date")[f"r{n}"].transform(lambda x: x.quantile(0.01))
        hi = pn.groupby("date")[f"r{n}"].transform(lambda x: x.quantile(0.99))
        pn[f"r{n}"] = pn[f"r{n}"].clip(lo, hi)
if MINCAP > 0:
    pn = pn[pn["mcap"] >= MINCAP]
pn["era"] = pd.cut(pn["date"].dt.year, [2010, 2015, 2020, 2030], labels=["2011-15", "2016-20", "2021~"]).astype(str)
SIG = {"GPA": "high", "ACC": "low", "AG": "low", "ISS": "low", "FS": "high", "EY": "high", "FCFY": "high", "RDCF": "low", "RGAP": "low", "RDCFD": "low"}
SIG = {k: v for k, v in SIG.items() if k in pn.columns}
if os.environ.get("ONLY"):                                  # 등록된 검정만 (예: ONLY=RDCFD)
    SIG = {k: SIG[k] for k in os.environ["ONLY"].split(",")}
CELLS = {"설계": ("A", "odd"), "확인1": ("A", "even"), "확인2": ("B", "odd"), "최종": ("B", "even")}


def per_date(df, sig, n):
    out = []
    for d, g in df.dropna(subset=[sig, f"r{n}"]).groupby("date"):
        if len(g) < 25: continue
        q = pd.qcut(g[sig].rank(method="first"), 5, labels=False)
        good = g[q == (4 if SIG[sig] == "high" else 0)]; bad = g[q == (0 if SIG[sig] == "high" else 4)]
        out.append({"date": d, "D": good[f"r{n}"].mean() - g[f"r{n}"].mean(), "LS": good[f"r{n}"].mean() - bad[f"r{n}"].mean(),
                    "raw": good[f"r{n}"].mean(), "n": len(g)})
    return pd.DataFrame(out)


def test(df, sig, n):
    u = per_date(df, sig, n)
    if len(u) < 6: return None
    m = smf.ols("D ~ 1", u).fit(cov_type="HAC", cov_kwds={"maxlags": 0 if n == 63 else 4})
    return {"dates": len(u), "D": m.params.iloc[0], "p1": 1 - norm.cdf(m.tvalues.iloc[0]), "LS": u["LS"].mean(),
            "net": u["raw"].mean() - 0.001, "avg_n": u["n"].mean()}


rows, logs = [], []
today = datetime.date.today().isoformat()
for sig in SIG:
    for n in (63, 252):
        res = {}
        for c, (g_, p_) in CELLS.items():
            if c != "설계" and not (res.get("설계") and res["설계"]["D"] > 0): break
            if c == "최종" and not (res["설계"]["net"] > 0 and all(res.get(x) and res[x]["D"] > 0 and res[x]["p1"] < 0.05 and res[x]["net"] > 0 for x in ("확인1", "확인2"))): break
            r = test(pn[(pn["grp"] == g_) & (pn["parity"] == p_)], sig, n)
            if r is None: break
            res[c] = r
        for c, r in res.items():
            rows.append({"signal": sig, "h": n, "cell": c, **r})
            logs.append([f"T5{TAG}-{sig}-{n}-{c}", today, 5, "재무 신호 좋은 쪽 5분위 − 전체", "Fundamental", sig, f"r{n}", c, r["dates"],
                         "D", round(r["D"], 5), "", "", round(r["p1"], 4), f"LS={round(r['LS'], 4)}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, f"results_{TAG}.csv"), index=False)

ref = []
dz = pn[pn["grp"] == "A"][pn["parity"] == "odd"]
for sig in SIG:
    for n in (63, 252):
        for col in ("era", "regime"):
            for v, sub in dz.groupby(col):
                u = per_date(sub, sig, n)
                if len(u): ref.append({"signal": sig, "h": n, "split": col, "value": v, "D": u["D"].mean(), "LS": u["LS"].mean()})
        u = per_date(pn, sig, n); ref.append({"signal": sig, "h": n, "split": "all", "value": "all", "D": u["D"].mean(), "LS": u["LS"].mean()})
ref = pd.DataFrame(ref); ref.to_csv(os.path.join(OUT, f"reference_{TAG}.csv"), index=False)
pd.set_option("display.width", 250, "display.float_format", "{:.4f}".format)
print(res.to_string(index=False))
print(ref.pivot_table(index=["signal", "h"], columns=["split", "value"], values="D").to_string())
