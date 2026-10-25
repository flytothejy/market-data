"""과제 2-4-01: Nasdaq-100 연말 재구성 (PLAN.md 규칙 그대로)."""
import os, json, hashlib, datetime
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); R2 = os.path.join(DATA, "raw", "r2")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task9", "out")
os.makedirs(OUT, exist_ok=True)
# 주식수 함수: 과제 1-5 R 패널과 같은 것(2026-10-25 수정판)
src = open(os.path.join(ROOT, "task5", "03_build_panel_R.py")).read().split("# ---------- 유니버스 ----------")[0]
gx = {"__file__": os.path.join(ROOT, "task5", "03_build_panel_R.py")}; exec(src, gx); shares = gx["shares"]

# ---------- 풀: 회사(CIK) 단위 ----------
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False); now2cik = dict(zip(cur["ticker"], cur["cik_str"]))
uni = pd.read_csv(os.path.join(DATA, "universe.csv")); uni["t2"] = uni["t"].str.replace(".", "-", regex=False)
prof = pd.read_parquet(os.path.join(R2, "profile__profile.parquet"))[["ticker", "country", "exchange"]]
prof["ticker"] = prof["ticker"].astype(str).str.replace(".", "-", regex=False); prof = prof.astype(object).where(prof.notna(), None).drop_duplicates("ticker").set_index("ticker")
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); dm = dm[dm["status"].isin(["unique", "still_filing_other_ticker"])]
sic = pd.read_csv(os.path.join(SB, "delisted_sic.csv")).set_index("cik")["sic"]
dl = pd.DataFrame(json.load(open(os.path.join(DATA, "raw", "eodhd", "us_delisted.json"))))
dl = dl[dl["Type"] == "Common Stock"].drop_duplicates("Code").set_index("Code")["Exchange"]
wm = pd.read_csv(os.path.join(SB, "ndx_wiki", "members.csv"))
wm["set"] = wm["tickers"].fillna("").map(lambda s: {x.strip().replace(".", "-") for x in s.split(",") if x.strip()})
ever = set().union(*wm["set"])
ENT = {}   # key -> (cik, path, nasdaq)
for t in uni["t2"]:
    if t not in now2cik or t not in prof.index or prof.at[t, "country"] != "United States": continue
    if uni.loc[uni["t2"] == t, "sec"].iloc[0] in ("Financial Services", "Real Estate"): continue
    p = os.path.join(PX, f"{t}.parquet")
    if os.path.exists(p): ENT[t] = (int(now2cik[t]), p, prof.at[t, "exchange"] in ("NMS", "NGM") or t in ever)
for r in dm.itertuples():
    sc = sic.get(int(r.cik))
    try: sc = int(sc)
    except (TypeError, ValueError): sc = None
    if sc is None or 6000 <= sc <= 6799: continue
    p = os.path.join(PXD, f"{r.code.replace('/', '_')}.parquet")
    base = r.code.split("_")[0]
    if os.path.exists(p): ENT["D:" + r.code] = (int(r.cik), p, dl.get(r.code) == "NASDAQ" or base in ever)
print("pool entities", len(ENT))
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
PXS = {k: pd.read_parquet(v[1])[["Close", "RawClose", "RawUnadj", "Volume"]].groupby(level=0).last().reindex(cal) for k, v in ENT.items()}

def last_td(y, m):
    d = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0); return cal[cal.searchsorted(d, side="right") - 1]
def eff_date(y):
    fr = [d for d in pd.date_range(f"{y}-12-01", f"{y}-12-31") if d.weekday() == 4][2]
    return cal[cal.searchsorted(fr, side="right")]

def snapshot(y):
    """10월 마지막 거래일 기준 나스닥 상장 회사(CIK) 시가총액 순위."""
    d = last_td(y, 10); pos = cal.get_loc(d); rows = []
    aug = last_td(y, 8)
    for k, (c, p, nas) in ENT.items():
        if not nas: continue
        px = PXS[k]; u = px["RawUnadj"].iloc[pos]
        if u != u: continue
        first = px["RawUnadj"].first_valid_index()
        if first is None or first > aug: continue
        w = px.iloc[pos - 62:pos + 1]
        if (w["RawClose"] * w["Volume"]).mean() < 5e6: continue
        sh = shares(c, d + pd.Timedelta(days=1))
        if sh != sh: continue
        rows.append({"key": k, "cik": c, "mcap": u * sh, "cur": not k.startswith("D:")})
    s = pd.DataFrame(rows)
    if s.empty: return s
    s = s.sort_values(["cik", "cur", "mcap"], ascending=[True, False, False]).drop_duplicates("cik")   # 같은 회사 한 번만
    s = s.sort_values("mcap", ascending=False).reset_index(drop=True); s["rank"] = np.arange(1, len(s) + 1)
    return s

def map_members(tickers, y, snap):
    """위키 티커 → CIK. 그 시점 가격이 있는 후보 중 시가총액이 큰 것."""
    d = last_td(y, 10); pos = cal.get_loc(d); out, miss = set(), []
    for t in tickers:
        cands = [k for k in ENT if k == t or k == "D:" + t or (k.startswith("D:" + t + "_"))]
        best, bm = None, -1
        for k in cands:
            u = PXS[k]["RawUnadj"].iloc[max(0, pos - 40):pos + 1].dropna()
            if len(u) == 0: continue
            m = snap.loc[snap["cik"] == ENT[k][0], "mcap"]
            v = m.iloc[0] if len(m) else 0
            if v > bm: best, bm = k, v
        if best is None: miss.append(t)
        else: out.add(ENT[best][0])
    return out, miss

recs, ev_rows, prev_rank = [], [], {}
for y in range(2011, 2026):
    snap = snapshot(y)
    pre = wm[(wm["year"] == y + 1) & (wm["tag"] == "pre")]["set"].iloc[0]
    post = wm[(wm["year"] == y + 1) & (wm["tag"] == "post")]["set"].iloc[0]
    mpre, miss_pre = map_members(pre, y, snap); mpost, miss_post = map_members(post, y, snap)
    slots = 100 - len(miss_pre)
    rk = dict(zip(snap["cik"], snap["rank"]))
    # B1
    order = list(snap["cik"])
    sel = order[:75]
    sel += [c for c in order[75:100] if c in mpre]
    sel += [c for c in order[100:125] if c in mpre and prev_rank.get(c, 999) <= 100]
    for c in order:
        if len(sel) >= slots: break
        if c not in sel and c not in mpre and rk[c] <= 100: sel.append(c)
    sel = set(sel[:max(slots, len(sel))])
    b0 = set(order[:slots])
    true_add = mpost - mpre; true_rem = mpre - mpost
    cand = set(order[:150]) - mpre
    for c in set(order[:150]) | mpre | mpost:
        recs.append({"year": y, "cik": c, "rank": rk.get(c, np.nan), "member": c in mpre,
                     "true_add": c in true_add, "true_rem": c in true_rem, "cand": c in cand,
                     "b1_add": c in sel - mpre, "b1_rem": c in mpre - sel, "b0_add": c in b0 - mpre, "b0_rem": c in mpre - b0,
                     "key": snap.loc[snap["cik"] == c, "key"].iloc[0] if c in rk else None})
    prev_rank = rk
    print(y, "pool ranked", len(snap), "| members mapped", len(mpre), "unmapped(pre)", len(miss_pre), "| true add/rem", len(true_add), len(true_rem),
          "| B1 add/rem", len(sel - mpre), len(mpre - sel), "| miss", ",".join(miss_pre[:12]))
R = pd.DataFrame(recs)
key_of = {}
for k, v in ENT.items(): key_of.setdefault(v[0], k if not k.startswith("D:") else key_of.get(v[0], k))
R["key"] = R["key"].fillna(R["cik"].map(key_of))
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
R["grp"] = [("A" if hashlib.md5(k[2:].encode()).digest()[0] % 2 == 0 else "B") if str(k).startswith("D:") else grp.get(k) for k in R["key"]]
R = R[R["grp"].notna()].copy()
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
R["cell"] = [names[(g, y % 2)] for g, y in zip(R["grp"], R["year"])]
R.to_csv(os.path.join(OUT, "records.csv"), index=False)

# ---------- 평가 ----------
def stats(d, pfx):
    ta, tr = d["true_add"], d["true_rem"]; pa, pr = d[f"{pfx}_add"], d[f"{pfx}_rem"]
    tp = (ta & pa).sum() + (tr & pr).sum(); fp = (pa & ~ta).sum() + (pr & ~tr).sum(); fn = (ta & ~pa).sum() + (tr & ~pr).sum()
    return {"prec_add": (ta & pa).sum() / max(pa.sum(), 1), "rec_add": (ta & pa).sum() / max(ta.sum(), 1),
            "prec_rem": (tr & pr).sum() / max(pr.sum(), 1), "rec_rem": (tr & pr).sum() / max(tr.sum(), 1),
            "f1": 2 * tp / max(2 * tp + fp + fn, 1), "n_add": int(ta.sum()), "n_rem": int(tr.sum()), "p_add": int(pa.sum()), "p_rem": int(pr.sum())}
T = {"B1_prec_add_vs_base": lambda d: stats(d, "b1")["prec_add"] - d.loc[d["cand"], "true_add"].mean(),
     "B1_prec_rem_vs_base": lambda d: stats(d, "b1")["prec_rem"] - d.loc[d["member"], "true_rem"].mean(),
     "B1_minus_B0_f1": lambda d: stats(d, "b1")["f1"] - stats(d, "b0")["f1"]}
rng = np.random.default_rng(20261025); rows, logs = [], []
today = datetime.date.today().isoformat()
for name, fn in T.items():
    res = {}
    for c in ("설계", "확인1", "확인2", "최종"):
        if c == "최종" and not all(res[x]["p1"] < 0.05 and res[x]["est"] > 0 for x in ("확인1", "확인2")): break
        sub = R[R["cell"] == c]; by = {y: g for y, g in sub.groupby("year")}; ys = list(by)
        est = fn(sub); bs = np.array([fn(pd.concat([by[y] for y in rng.choice(ys, len(ys))])) for _ in range(2000)])
        res[c] = {"est": est, "p1": float((bs <= 0).mean()), "years": len(ys), **{f"b1_{k}": v for k, v in stats(sub, "b1").items()},
                  **{f"b0_{k}": v for k, v in stats(sub, "b0").items()}}
    for c, r in res.items():
        rows.append({"test": name, "cell": c, **r})
        logs.append([f"T9-{name}-{c}", today, 9, "Nasdaq-100 연말 재구성 예측", "NDX", name, "add/rem", c, r["years"], name,
                     round(r["est"], 5), 0, "", round(r["p1"], 4), f"n_add={r['b1_n_add']};n_rem={r['b1_n_rem']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
res = pd.DataFrame(rows); res.to_csv(os.path.join(OUT, "results.csv"), index=False)
allst = {p: stats(R, p) for p in ("b1", "b0")}; json.dump(allst, open(os.path.join(OUT, "overall.json"), "w"), indent=1, default=float)
print(json.dumps(allst, default=float, indent=0))

# ---------- 반응 확인 ----------
ev = []
for r in R[R["true_add"] | R["true_rem"] | R["b1_add"]].itertuples():
    k = r.key
    if k not in PXS: continue
    lc = np.log(PXS[k]["Close"].values); y = r.year
    e = cal.get_loc(eff_date(y)); a = e - 5; s0 = cal.searchsorted(pd.Timestamp(y, 11, 1))
    def car(i, j):
        if i < 1 or j >= len(cal) or not (np.isfinite(lc[i - 1]) and np.isfinite(lc[j])): return np.nan
        return (np.exp(lc[j] - lc[i - 1]) - 1) - (np.exp(ls[j] - ls[i - 1]) - 1)
    kind = "편입" if r.true_add else "편출" if r.true_rem else "예측 편입·실제 아님"
    ev.append({"year": y, "key": k, "kind": kind, "b1_add": r.b1_add, "pre_nov1_to_ann": car(s0, a - 1), "react01": car(a, a + 1),
               "run_to_eff": car(a + 2, e - 1), "post20": car(e, e + 20)})
EV = pd.DataFrame(ev); EV.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
EV["grp"] = EV["kind"] + np.where((EV["kind"] == "편입") & EV["b1_add"], "(예측함)", np.where(EV["kind"] == "편입", "(예측 못함)", ""))
es = EV.groupby("grp")[["pre_nov1_to_ann", "react01", "run_to_eff", "post20"]].agg(["count", "mean", "median"])
es.to_csv(os.path.join(OUT, "event_summary.csv"))
pd.set_option("display.width", 250, "display.float_format", "{:.4f}".format)
print(res[["test", "cell", "est", "p1", "years", "b1_prec_add", "b1_rec_add", "b1_prec_rem", "b1_rec_rem", "b1_f1", "b0_f1", "b1_n_add", "b1_n_rem"]].to_string(index=False))
print(es.to_string())
