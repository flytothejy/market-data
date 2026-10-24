"""과제 3-01: 예측일 × 종목 패널 만들기 (PLAN.md §2·§3).
출력: research/data/task3_panel.csv, research/task3/out/additions.csv (편입 건별로 우리 풀에 있었는지)
"""
import os, json, re
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); R2 = os.path.join(DATA, "raw", "r2")
PX = os.path.join(DATA, "prices"); OUT = os.path.join(ROOT, "task3", "out"); os.makedirs(OUT, exist_ok=True)

# ---------- 티커 연결 (옛 티커 → 현재 티커) ----------
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False)
cik2now = dict(zip(cur["cik_str"], cur["ticker"])); now2cik = {v: k for k, v in cik2now.items()}
wm = pd.read_csv(os.path.join(SB, "wiki_members_hist.csv")).dropna(subset=["cik"])
wm["t"] = wm["t"].astype(str).str.replace(".", "-", regex=False)
alias = {}
for t, c in wm.groupby("t")["cik"].first().items():
    n = cik2now.get(int(c))
    if n and n != t:
        alias[t] = n
norm = lambda t: alias.get(t.replace(".", "-"), t.replace(".", "-"))

h = pd.read_csv(os.path.join(SB, "sp500_hist.csv"), parse_dates=["date"])
h = h[h["date"] >= "2009-01-01"].reset_index(drop=True)
hs = [set(norm(x) for x in s.split(",")) for s in h["tickers"]]
hd = list(h["date"].values)
# 구성 종목 파일은 2025-08-23에서 멈춤 → 이후는 위키백과 변경 내역(2026-05-23 판본)으로 이어 붙인다 (PLAN 변경 이력)
HIST_END = pd.Timestamp(hd[-1]); TRUTH_END = pd.Timestamp("2026-05-23")
wc = pd.read_csv(os.path.join(SB, "wiki_changes.csv")); wc["date"] = pd.to_datetime(wc["date"], errors="coerce")
wc = wc[(wc["date"] > HIST_END) & (wc["date"] <= TRUTH_END)].sort_values("date")
for d, g in wc.groupby("date"):
    s = set(hs[-1])
    s -= {norm(x) for x in g["rem_t"].dropna()}
    s |= {norm(x) for x in g["add_t"].dropna()}
    hs.append(s); hd.append(np.datetime64(d))
hd = np.array(hd, dtype="datetime64[ns]")
print("membership through", TRUTH_END.date(), "| appended wiki change dates:", wc["date"].nunique())

def members_at(d):
    i = np.searchsorted(hd, np.datetime64(d), side="right") - 1
    return hs[i] if i >= 0 else set()

# 편입 이벤트 (효력일, 현재 티커)
adds = []
for i in range(1, len(hs)):
    for t in hs[i] - hs[i - 1]:
        adds.append((pd.Timestamp(hd[i]), t))
adds = pd.DataFrame(adds, columns=["date", "t"])

# ---------- 유니버스·본사 ----------
uni = pd.read_csv(os.path.join(DATA, "universe.csv"))
prof = pd.read_parquet(os.path.join(R2, "profile__profile.parquet"))[["ticker", "country"]]
us = set(prof.loc[prof["country"] == "United States", "ticker"].str.replace(".", "-", regex=False))
pool_t = [t.replace(".", "-") for t in uni["t"] if t.replace(".", "-") in us
          and os.path.exists(os.path.join(PX, f"{t.replace('.', '-')}.parquet"))]
print("pool tickers (US, priced):", len(pool_t))

# ---------- SEC: 발행주식수, 분기 순이익 (최초 공시일 기준) ----------
f = pd.read_parquet(os.path.join(R2, "sec__facts.parquet"), columns=["cik", "tag", "start", "end", "fp", "form", "filed", "val"])
f["filed"] = pd.to_datetime(f["filed"]); f["end"] = pd.to_datetime(f["end"]); f["start"] = pd.to_datetime(f["start"])
sh = f[f["tag"] == "EntityCommonStockSharesOutstanding"].sort_values("filed")
# 보완: 표지 발행주식수가 없을 때 희석 가중평균 주식수 (PLAN 변경 이력 2026-10-24)
wad = pd.read_parquet(os.path.join(R2, "sec__facts.parquet"), columns=["cik", "tag", "filed", "val"])
wad = wad[wad["tag"] == "WeightedAverageNumberOfDilutedSharesOutstanding"].copy()
wad["filed"] = pd.to_datetime(wad["filed"]); wad = wad.sort_values("filed")
wad_by = {c: g[["filed", "val"]] for c, g in wad.groupby("cik")}
ni = f[f["tag"] == "NetIncomeLoss"].copy()
ni["dur"] = (ni["end"] - ni["start"]).dt.days
first = ni.sort_values("filed").drop_duplicates(["cik", "start", "end"], keep="first")
q = first[first["dur"].between(80, 100)][["cik", "end", "filed", "val"]]
fy = first[first["dur"].between(350, 380)][["cik", "start", "end", "filed", "val"]]
ytd9 = first[first["dur"].between(260, 285)][["cik", "start", "end", "val"]]
q4 = fy.merge(ytd9, on=["cik", "start"], suffixes=("", "_9m"))
q4 = q4[(q4["end"] - q4["end_9m"]).dt.days.between(80, 100)]
q4 = pd.DataFrame({"cik": q4["cik"], "end": q4["end"], "filed": q4["filed"], "val": q4["val"] - q4["val_9m"]})
qs = pd.concat([q, q4]).sort_values(["cik", "end", "filed"]).drop_duplicates(["cik", "end"], keep="first")
qs_by = {c: g.sort_values("end") for c, g in qs.groupby("cik")}
sh_by = {c: g[["filed", "val"]] for c, g in sh.groupby("cik")}

def earn_ok(cik, d):
    g = qs_by.get(cik)
    if g is None:
        return np.nan
    g = g[g["filed"] < d]
    if len(g) < 4:
        return np.nan
    last4 = g.tail(4)
    if (last4["end"].iloc[-1] - last4["end"].iloc[0]).days > 300:      # 연속 4분기 아님
        return np.nan
    return float(last4["val"].iloc[-1] > 0 and last4["val"].sum() > 0)

def shares(cik, d):
    for src in (sh_by, wad_by):
        g = src.get(cik)
        if g is None:
            continue
        g = g[(g["filed"] < d) & (g["filed"] >= d - pd.Timedelta(days=200))]   # 최근 공시만 (오래된 값 배제)
        if len(g):
            return g["val"].iloc[-1]
    return np.nan

# ---------- 예측일 ----------
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))
cal = spy.index
dates = []
for y in range(2010, 2027):
    for m in (1, 4, 7, 10):
        d = pd.Timestamp(y, m, 1)
        if pd.Timestamp("2010-07-01") <= d <= pd.Timestamp("2026-01-01"):     # 3개월 정답 창이 TRUTH_END 안에 들어오는 날까지
            dates.append(cal[cal.searchsorted(d)])
nxt = {d: (dates[i + 1] if i + 1 < len(dates) else d + pd.Timedelta(days=91)) for i, d in enumerate(dates)}

pxc = {t: pd.read_parquet(os.path.join(PX, f"{t}.parquet")).reindex(cal) for t in pool_t}
spyc = spy["Close"]
rows = []
for d in dates:
    mem = members_at(d - pd.Timedelta(days=1))
    pos = cal.get_loc(d); e3 = cal[min(cal.searchsorted(nxt[d]), len(cal) - 1)]
    a3 = set(adds[(adds["date"] > d) & (adds["date"] <= nxt[d])]["t"])
    a12 = set(adds[(adds["date"] > d) & (adds["date"] <= d + pd.Timedelta(days=365))]["t"])   # 2025-05 이후 예측일은 12개월 창이 잘림
    for t in pool_t:
        if t in mem:
            continue
        p = pxc[t]
        c = p["RawUnadj"].iloc[:pos].dropna()          # 분할 미반영 실제 주가 (2026-10-25 오류 수정)
        if c.empty:
            continue
        firstpx = p["RawClose"].first_valid_index()
        if firstpx is None or firstpx > d - pd.Timedelta(days=365):
            continue
        cik = now2cik.get(t)
        s_ = shares(cik, d) if cik else np.nan
        mc = c.iloc[-1] * s_ if s_ == s_ else np.nan
        win = p.iloc[max(0, pos - 252):pos]
        mv = win["Volume"].groupby(win.index.to_period("M")).sum().tail(6)
        dv = (win["RawClose"] * win["Volume"]).sum()
        liq = float(len(mv) == 6 and (mv >= 250_000).all() and mc == mc and dv / mc >= 0.75) if mc == mc else np.nan
        cl = p["Close"]
        r3 = cl.loc[e3] / cl.iloc[pos] - 1 if pd.notna(cl.loc[e3]) and pd.notna(cl.iloc[pos]) else np.nan
        s3 = spyc.loc[e3] / spyc.iloc[pos] - 1
        rows.append({"date": d, "t": t, "mcap": mc, "earn_ok": earn_ok(cik, d) if cik else np.nan, "liq_ok": liq,
                     "add3": int(t in a3), "add12": int(t in a12), "raw3": r3, "ab3": r3 - s3 if r3 == r3 else np.nan})
    print(d.date(), len(rows), flush=True)

pn = pd.DataFrame(rows)
pn.to_csv(os.path.join(DATA, "task3_panel.csv"), index=False)
# 편입 건별로 우리 풀에 있었는지
inpool = set(pool_t)
ad = adds[(adds["date"] > dates[0]) & (adds["date"] <= nxt[dates[-1]])].copy()
ad["in_pool"] = ad["t"].isin(inpool)
ad["in_panel_prev"] = [((pn["date"] < r.date) & (pn["t"] == r.t)).any() for r in ad.itertuples()]
ad.to_csv(os.path.join(OUT, "additions.csv"), index=False)
print("additions:", len(ad), "in pool:", int(ad["in_pool"].sum()), "in panel before:", int(ad["in_panel_prev"].sum()))
print("panel rows", len(pn), "mcap known", pn["mcap"].notna().mean().round(3), "earn known", pn["earn_ok"].notna().mean().round(3))
