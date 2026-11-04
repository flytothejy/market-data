"""과제 2-9-01: 주도 섹터·자산 신호 계산 + 사전 등록 검정 (PLAN.md).

입력: R2DL 폴더(px_YYYY.parquet, company.parquet, insider_hist.parquet), task13/out/fund.parquet,
      data/universe.csv, task14/data/{btcusd,ethusd}.csv
출력: task14/out/{monthly.parquet, ic.parquet, results.csv, design_splits.csv}
"""
import os, glob, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T14 = os.path.join(ROOT, "task14")
OUT = os.path.join(T14, "out"); os.makedirs(OUT, exist_ok=True)
R2 = os.environ["R2DL"]

G = {
    "G1": "XLB XLE XLF XLI XLK XLP XLU XLV XLY".split(),
    "G2": "SMH IGV XBI KRE ITB ITA OIH XOP GDX TAN VNQ".split(),
    "G3": "EWJ EWG EWU FXI EWZ EWY EWT".split(),
    "G4": "SHY IEF TLT TIP LQD HYG EMB MUB".split(),
    "G5": "GLD SLV USO UNG DBC".split(),
    "G6": "SPY EFA EEM IEF TLT HYG GLD DBC VNQ BTC ETH".split(),
}
ALL = sorted(set(sum(G.values(), [])) - {"BTC", "ETH"})

# ---------- 가격 ----------
px = pd.concat([pd.read_parquet(p, columns=["date", "ticker", "adj_close"]) for p in sorted(glob.glob(os.path.join(R2, "px_20*.parquet")))])
px = px[px["ticker"].isin(ALL)]
px["date"] = pd.to_datetime(px["date"])
P = px.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
cal = P.index
for c, f in [("BTC", "btcusd.csv"), ("ETH", "ethusd.csv")]:
    s = pd.read_csv(os.path.join(T14, "data", f), parse_dates=["date"]).set_index("date")["close"]
    P[c] = s.reindex(cal, method="ffill").where(cal >= s.index.min())
P = P[P.index <= "2026-10-31"]
ME = P.groupby(P.index.to_period("M")).apply(lambda d: d.index.max())  # 월말 거래일
ME = pd.DatetimeIndex(ME.values)
M = P.loc[ME]                                   # 월말 가격
HI = P.rolling(252, min_periods=240).max().loc[ME]

sig = {}
sig["MOM"] = M.shift(1) / M.shift(12) - 1
sig["REV"] = -(M / M.shift(1) - 1)              # 좋은 쪽 = 낮음 → 부호 뒤집어 '높을수록 좋음'
sig["HI52"] = M / HI
fwd3 = M.shift(-3) / M - 1
fwd1 = M.shift(-1) / M - 1
ts12 = M / M.shift(12) - 1

# ---------- 섹터 재무·내부자 확산도 (G1) ----------
SECMAP = {"Basic Materials": "XLB", "Energy": "XLE", "Financial Services": "XLF", "Industrials": "XLI", "Technology": "XLK",
          "Consumer Defensive": "XLP", "Utilities": "XLU", "Healthcare": "XLV", "Consumer Cyclical": "XLY"}
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
uni["etf"] = uni["sec"].map(SECMAP)
t2e = dict(zip(uni["t"], uni["etf"]))
fund = pd.read_parquet(os.path.join(T14, "..", "task13", "out", "fund.parquet"))
fund = fund.sort_values(["t", "F"])
fund["acc"] = (fund["rev_g"] > fund.groupby("t")["rev_g"].shift(1)).where(fund["rev_g"].notna() & fund.groupby("t")["rev_g"].shift(1).notna())
fund["etf"] = fund["t"].map(t2e)
fund = fund.dropna(subset=["etf"])
for k in ["REVACC", "INVW", "ISSN", "INSB"]:
    sig[k] = pd.DataFrame(np.nan, index=ME, columns=M.columns)
for d in ME:
    w = fund[(fund["F"] <= d) & (fund["F"] > d - pd.Timedelta(days=120))].drop_duplicates("t", keep="last")
    for e, g in w.groupby("etf"):
        if e == "XLF":
            continue
        a = g["acc"].dropna(); i = g["INV"].dropna(); s = g["iss_g"].dropna()
        if len(a) >= 8: sig["REVACC"].loc[d, e] = a.mean()
        if len(i) >= 8: sig["INVW"].loc[d, e] = -i.mean()
        if len(s) >= 8: sig["ISSN"].loc[d, e] = -s.median()
co = pd.read_parquet(os.path.join(R2, "company.parquet"))
cik2t = dict(zip(co["cik"], co["ticker"]))
ins = pd.read_parquet(os.path.join(R2, "insider_hist.parquet"), columns=["cik", "filed", "code"])
ins = ins[ins["code"] == "P"].copy()
ins["t"] = ins["cik"].map(cik2t); ins["etf"] = ins["t"].map(t2e); ins = ins.dropna(subset=["etf"])
ins["filed"] = pd.to_datetime(ins["filed"])
nfirm = uni.dropna(subset=["etf"]).groupby("etf")["t"].nunique()
for d in ME:
    if d < pd.Timestamp("2010-04-01"):
        continue                                     # 내부자 이력은 2010-01부터 → 90일 창이 찬 뒤부터
    w = ins[(ins["filed"] <= d) & (ins["filed"] > d - pd.Timedelta(days=90))]
    cnt = w.groupby("etf")["t"].nunique()
    sig["INSB"].loc[d] = (cnt.reindex(nfirm.index).fillna(0) / nfirm).reindex(M.columns)

# ---------- 칸 ----------
cell = pd.Series(index=ME, dtype=object)
for d in ME:
    nxt = d + pd.offsets.MonthEnd(1)
    y = nxt.year
    crosses = (d + pd.offsets.MonthEnd(3)).year != y
    if 2007 <= y <= 2016:
        if crosses:
            continue
        cell[d] = "설계" if y % 2 == 1 else "확인1"
    elif 2017 <= y <= 2021:
        cell[d] = "확인2"
    elif y >= 2022 and d <= pd.Timestamp("2026-07-31"):
        cell[d] = "최종"
spy = P["SPY"]; ma = spy.rolling(200).mean()
regime = pd.Series(np.where(spy.loc[ME] > ma.loc[ME], "up", "down"), index=ME)

# ---------- 월별 IC ----------
REQ = {"G1": ["MOM", "REV", "HI52", "REVACC", "INVW", "ISSN", "INSB"]}
recs = []
for gname, mem in G.items():
    for s in REQ.get(gname, ["MOM", "REV", "HI52"]):
        for d in ME:
            if pd.isna(cell.get(d)):
                continue
            x = sig[s].loc[d, mem]; y3 = fwd3.loc[d, mem]; y1 = fwd1.loc[d, mem]
            # 13개월 이력 요건: MOM 계산 가능한 상품만
            ok = x.notna() & y3.notna() & sig["MOM"].loc[d, mem].notna()
            if ok.sum() < 4:
                continue
            xs, ys = x[ok], y3[ok]
            ic = xs.rank().corr(ys.rank())
            ic1 = xs.rank().corr(y1[ok].rank()) if y1[ok].notna().all() else np.nan
            k = max(1, int(round(ok.sum() / 3)))
            o = xs.sort_values()
            spread = ys[o.index[-k:]].mean() - ys[o.index[:k]].mean() - 0.002   # 상·하위 각각 왕복 0.1%
            mixed = np.nan
            if s not in ("MOM", "REV", "HI52"):
                mm = sig["MOM"].loc[d, mem][ok]
                mixed = (xs.rank() + mm.rank()).rank().corr(ys.rank()) - mm.rank().corr(ys.rank())
            recs.append({"group": gname, "signal": s, "date": d, "cell": cell[d], "regime": regime[d], "n": int(ok.sum()),
                         "ic": ic, "ic1": ic1, "spread": spread, "mix_gain": mixed})
IC = pd.DataFrame(recs)
IC.to_parquet(os.path.join(OUT, "ic.parquet"))


def nw_mean(x, lag=2):
    x = pd.Series(x).dropna()
    if len(x) < 12:
        return np.nan, np.nan, np.nan
    m = sm.OLS(x.values, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    return m.params[0], m.tvalues[0], 1 - norm.cdf(m.tvalues[0])


def summ(df):
    m, t, p = nw_mean(df["ic"])
    sm_, st, _ = nw_mean(df["spread"])
    return {"months": len(df), "assets": df["n"].mean(), "IC": m, "t": t, "p1": p, "spread": sm_, "spread_t": st,
            "hit": (df["ic"] > 0).mean(), "IC1": df["ic1"].mean(), "mix_gain": df["mix_gain"].mean()}


# ---------- 추세 TS (상품별 평균 제거, 월 군집) ----------
def ts_test(dates):
    rows = []
    for a in sorted(set(sum(G.values(), []))):
        for d in dates:
            if pd.notna(ts12.loc[d, a]) and pd.notna(fwd3.loc[d, a]):
                rows.append((a, d, float(ts12.loc[d, a] > 0), fwd3.loc[d, a]))
    D = pd.DataFrame(rows, columns=["a", "d", "S", "y"])
    if len(D) < 100:
        return None
    vol = D.groupby("a")["y"].transform("std")
    D["y"] = D["y"] / vol                               # 상품별 변동성으로 나눔 (원자재·암호화폐가 지배하지 않게)
    D["y"] = D["y"] - D.groupby("a")["y"].transform("mean")
    D["S"] = D["S"] - D.groupby("a")["S"].transform("mean")
    m = sm.OLS(D["y"], sm.add_constant(D["S"])).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(D["d"])[0]})
    return {"months": D["d"].nunique(), "assets": D["a"].nunique(), "IC": m.params["S"], "t": m.tvalues["S"],
            "p1": 1 - norm.cdf(m.tvalues["S"]), "spread": np.nan, "spread_t": np.nan, "hit": np.nan, "IC1": np.nan, "mix_gain": np.nan}


rows, logs = [], []
today = datetime.date.today().isoformat()
keys = [(g, s) for g in G for s in REQ.get(g, ["MOM", "REV", "HI52"])] + [("ALL", "TS")]
for g, s in keys:
    def get(c):
        if s == "TS":
            return ts_test(cell[cell == c].index)
        d = IC[(IC["group"] == g) & (IC["signal"] == s) & (IC["cell"] == c)]
        return summ(d) if len(d) >= 12 else None
    res = {"설계": get("설계")}
    if res["설계"] and res["설계"]["IC"] > 0:
        for c in ["확인1", "확인2"]:
            res[c] = get(c)
        ok = all(res[c] and res[c]["IC"] > 0 and res[c]["p1"] < 0.05 and (s == "TS" or res[c]["spread"] > 0) for c in ["확인1", "확인2"])
        if ok:
            res["최종"] = get("최종")
    for c, r in res.items():
        if r is None:
            continue
        rows.append({"group": g, "signal": s, "cell": c, **r})
        logs.append([f"T14-{g}-{s}-{c}", today, "2-9", "주도 섹터·자산 고르기", s, g, "fwd3", c, r["months"],
                     "IC" if s != "TS" else "beta", round(r["IC"], 5), "0", "", round(r["p1"], 4), f"spread={r['spread']:.4f}" if pd.notna(r["spread"]) else ""])
R = pd.DataFrame(rows)
R.to_csv(os.path.join(OUT, "results.csv"), index=False)
with open(os.path.join(ROOT, "log.csv"), "a") as f:
    for l in logs:
        f.write(",".join(str(x) for x in l) + "\n")

ref = []
for (g, s), d in IC[IC["cell"] == "설계"].groupby(["group", "signal"]):
    for v, dd in d.groupby("regime"):
        r = summ(dd); ref.append({"group": g, "signal": s, "regime": v, **r})
pd.DataFrame(ref).to_csv(os.path.join(OUT, "design_splits.csv"), index=False)
pd.set_option("display.width", 220)
print(R[["group", "signal", "cell", "months", "assets", "IC", "t", "p1", "spread", "spread_t", "hit", "IC1", "mix_gain"]].round(3).to_string(index=False))
