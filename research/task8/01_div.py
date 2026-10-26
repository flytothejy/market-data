"""과제 2-3-01: 배당 증액·삭감 (PLAN.md 규칙 그대로). 정리 → 반응 확인(가) → 사전 예측(나)."""
import os, json, glob, hashlib, datetime
import numpy as np, pandas as pd
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); DV = os.path.join(DATA, "raw", "eodhd", "div")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted_clean"); OUT = os.path.join(ROOT, "task8", "out" + os.environ.get("TAG", ""))
os.makedirs(OUT, exist_ok=True)
spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
def prices(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    if not os.path.exists(p): return None
    d = pd.read_parquet(p).groupby(level=0).last().reindex(cal)
    return d

# ---------- 정기 분기 배당 정리 ----------
pn = pd.read_csv(os.path.join(DATA, "task5_panel_R.csv"), parse_dates=["date"]).sort_values("date")
rows = []
for t in pn["t"].unique():
    f = os.path.join(DV, t.replace(":", "_").replace("/", "_") + ".json")
    try: j = json.load(open(f))
    except Exception: continue
    if not isinstance(j, list) or len(j) < 6: continue
    d = pd.DataFrame(j)
    d = d[(d["currency"].fillna("USD") == "USD") & (d["value"] > 0)].copy()
    d["date"] = pd.to_datetime(d["date"]); d = d.sort_values("date").drop_duplicates("date")
    keep, last = [], None
    for i, r in d.iterrows():
        if last is not None and (r["date"] - last).days < 45: continue
        if os.environ.get("SPECIAL25") == "1" and len(keep) >= 3:
            # 2026-10-26 사후(구현 쪽 확인 4): 직전 정기 배당 3~4회 중앙값의 2.5배를 넘으면 특별배당
            if r["value"] > 2.5 * d.loc[keep[-4:], "value"].median(): continue
        keep.append(i); last = r["date"]
    d = d.loc[keep]
    if len(d) < 6 or not (80 <= d["date"].diff().dt.days.median() <= 100): continue
    d["t"] = t; rows.append(d[["t", "date", "declarationDate", "value", "unadjustedValue"]])
D = pd.concat(rows, ignore_index=True)
D["decl"] = pd.to_datetime(D["declarationDate"], errors="coerce")
print("quarterly payers:", D["t"].nunique(), "dividends:", len(D))

# ---------- 사건·목표·특징 (회사별) ----------
ev, smp = [], []
for t, g in D.groupby("t"):
    g = g.reset_index(drop=True); px = prices(t)
    if px is None: continue
    raw = px["RawUnadj"].values; lc = np.log(px["Close"].values)
    lastpx = px["Close"].last_valid_index()
    v = g["value"].values; dt = g["date"].values
    chg = np.r_[np.nan, np.where(v[1:] > v[:-1] * 1.005, 1, np.where(v[1:] < v[:-1] * 0.995, -1, 0))]
    for k in range(len(g)):
        # 가. 선언일 반응 (k번째 배당의 변화)
        if k >= 1 and pd.notna(g.at[k, "decl"]):
            pos = cal.searchsorted(g.at[k, "decl"])
            if 6 <= pos < len(cal) - 1:
                def car(a, b):
                    s, e = pos + a - 1, pos + b
                    if not (np.isfinite(lc[s]) and np.isfinite(lc[e])): return np.nan
                    return (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
                ev.append({"t": t, "decl": g.at[k, "decl"], "chg": chg[k], "car01": car(0, 1), "carm5m1": car(-5, -1)})
        # 나. 예측 표본 (k번째 배당락일 다음 날 시점)
        d0 = pd.Timestamp(dt[k]); pd0 = d0 + pd.Timedelta(days=1)
        if not (pd.Timestamp("2011-01-01") <= pd0 <= pd.Timestamp("2025-09-30")) or k < 4: continue
        r = {"t": t, "date": pd0, "exdate": d0}
        # 목표 1
        if k + 1 < len(g) and (pd.Timestamp(dt[k + 1]) - d0).days <= 150: r["y_up"] = int(chg[k + 1] == 1)
        else: r["y_up"] = np.nan
        # 목표 2
        end = pd0 + pd.Timedelta(days=365)
        if pd0 <= pd.Timestamp("2024-10-01") and lastpx is not None and lastpx >= end + pd.Timedelta(days=150):
            fut = g[(g["date"] > d0) & (g["date"] <= end)]
            cut = bool((fut["value"].values < v[k] * 0.995).any()) if len(fut) else False
            # 중단: 창 안의 어떤 배당(이번 포함) 뒤 150일 넘게 다음 배당이 없음 (그 150일째가 창 안에 오고, 주가는 계속 거래)
            after = list(g[g["date"] > d0]["date"])
            seq = [d0] + after
            omit = False
            for i, a in enumerate(seq):
                if a > end: break
                b = seq[i + 1] if i + 1 < len(seq) else lastpx
                if (b - a).days > 150 and a + pd.Timedelta(days=150) <= end: omit = True; break
            r["y_cut"] = int(cut or omit)
        else: r["y_cut"] = np.nan
        r["u_anniv"] = float(chg[k - 3] == 1) if k - 3 >= 1 else np.nan
        r["u_n4"] = float(np.nansum(chg[k - 3:k + 1] == 1))
        cuts = [pd.Timestamp(dt[i]) for i in range(1, k + 1) if chg[i] == -1]
        since = pd.Timestamp(dt[0]) if not cuts else cuts[-1]
        r["u_streak"] = min((d0 - since).days / 365.25, 15)
        pos = cal.searchsorted(d0)
        r["d_yield"] = g.at[k, "unadjustedValue"] * 4 / raw[pos] if pos < len(cal) and np.isfinite(raw[pos]) and raw[pos] > 0 else np.nan
        e, s = pos - 1, pos - 253
        r["d_ret"] = ((np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)) if s >= 0 and np.isfinite(lc[s]) and np.isfinite(lc[e]) else np.nan
        smp.append(r)
EV = pd.DataFrame(ev); S = pd.DataFrame(smp)
# 실적 발표 겹침 표시
er = pd.read_csv(os.path.join(DATA, "events_R.csv"), usecols=["t", "rday"], parse_dates=["rday"])
erset = {(t, d) for t, d in zip(er["t"], er["rday"])}
EV["earn_overlap"] = [any((t, d + pd.Timedelta(days=o)) in erset for o in (-1, 0, 1, 2, 3)) for t, d in zip(EV["t"], EV["decl"])]
EV.to_csv(os.path.join(OUT, "decl_events.csv"), index=False)
es = []
for ov in (None, False):
    sub = EV if ov is None else EV[~EV["earn_overlap"]]
    for c, nm in ((1, "증액"), (0, "동일"), (-1, "삭감")):
        x = sub[sub["chg"] == c]
        es.append({"sample": "전체" if ov is None else "실적 겹침 제외", "chg": nm, "n": int(x["car01"].notna().sum()),
                   "car01_mean": x["car01"].mean(), "car01_median": x["car01"].median(), "pre_mean": x["carm5m1"].mean()})
ES = pd.DataFrame(es); ES.to_csv(os.path.join(OUT, "event_study.csv"), index=False)
print(ES.round(4).to_string(index=False))

# 재무: 예측 시점 직전 분기 초 패널 행
src = open(os.path.join(ROOT, "task5", "05_build_rdcf_D.py")).read().split("# ---------- 시장 입력 ----------")[0]
gx = {"__file__": os.path.join(ROOT, "task5", "05_build_rdcf_D.py")}; exec(src, gx); inst, first_ = gx["inst"], gx["first"]
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
now2cik = dict(zip(cur["ticker"].str.replace(".", "-", regex=False), cur["cik_str"]))
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv")); d2cik = dict(zip("D:" + dm["code"], dm["cik"]))
P = pn[pn["t"].isin(S["t"].unique())][["t", "date", "mcap", "EY", "FCFY"]].copy()
lev = []
for t, d in zip(P["t"], P["date"]):
    c = d2cik.get(t) if t.startswith("D:") else now2cik.get(t)
    if c is None or c != c: lev.append(np.nan); continue
    a = inst(int(c), "Assets", d); debt = first_(inst(int(c), "LongTermDebtNoncurrent", d), inst(int(c), "LongTermDebt", d))
    lev.append(debt / a if a and a == a and debt == debt else np.nan)
P["d_lev"] = lev
S = S.sort_values("date"); P = P.sort_values("date").rename(columns={"date": "pdate"})
S = pd.merge_asof(S, P, left_on="date", right_on="pdate", by="t", direction="backward", tolerance=pd.Timedelta(days=100))
S["d_size"] = np.log(S["mcap"].where(S["mcap"] > 0))
S["d_payout"] = np.where(S["EY"] > 0, S["d_yield"] / S["EY"], np.nan)
S["d_fcfcov"] = np.where(S["d_yield"] > 0, S["FCFY"] / S["d_yield"], np.nan)
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv")); grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
S["grp"] = [("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") if t.startswith("D:") else grp.get(t) for t in S["t"]]
S = S[S["grp"].notna()].copy()
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
S["cell"] = [names[(g_, y % 2)] for g_, y in zip(S["grp"], S["date"].dt.year)]
S["q"] = S["date"].dt.to_period("Q").astype(str); S["m"] = S["date"].dt.to_period("M").astype(str)
U = ["u_anniv", "u_n4", "u_streak"]; Dd = ["d_yield", "d_ret", "d_payout", "d_fcfcov", "d_lev", "d_size"]
dz = S[S["cell"] == "설계"]
for c in ("d_yield", "d_payout", "d_fcfcov", "d_ret"):
    lo, hi = dz[c].quantile([0.01, 0.99]); S[c] = S[c].clip(lo, hi)
dz = S[S["cell"] == "설계"]; med = dz[U + Dd].median()
for c in U + Dd:
    S[f"m_{c}"] = S[c].isna().astype(float); S[c] = S[c].fillna(med[c])
ALL = U + Dd + [f"m_{c}" for c in U + Dd]
S.to_csv(os.path.join(DATA, "task8_samples" + os.environ.get("TAG", "") + ".csv"), index=False)

def fitpred(y, cols):
    dz = S[(S["cell"] == "설계") & S[y].notna()]
    cols = [c for c in cols if dz[c].std() > 0]
    m = sm.Logit(dz[y], sm.add_constant(dz[cols])).fit(disp=0, maxiter=200)
    return m, m.predict(sm.add_constant(S[cols], has_constant="add"))
def top10(df, col, y):
    k = df[col] >= df.groupby("q")[col].transform(lambda x: x.quantile(0.9))
    return df.loc[k, y].mean()
rng = np.random.default_rng(20261025)
def boot(df, fn, B=2000):
    by = {m: g for m, g in df.groupby("m")}; ms = list(by)
    out = []
    for _ in range(B):
        s = pd.concat([by[m] for m in rng.choice(ms, len(ms))])
        try: out.append(fn(s))
        except ValueError: pass
    return np.array(out)
models, res_rows, logs = {}, [], []
today = datetime.date.today().isoformat()
for y, b1cols in (("y_up", ["u_anniv", "u_n4", "m_u_anniv"]), ("y_cut", None)):
    if b1cols is None: S["pB1_" + y] = S["d_yield"]; mb = None
    else: mb, S["pB1_" + y] = fitpred(y, b1cols)
    mm, S["pM_" + y] = fitpred(y, ALL)
    models[y] = {"B1": None if mb is None else mb.params.to_dict(), "M": mm.params.to_dict(),
                 "base_design": float(S[(S["cell"] == "설계")][y].mean())}
    a, b = "pB1_" + y, "pM_" + y
    T = {"B1_auc": (lambda d: roc_auc_score(d[y], d[a]), 0.5),
         "M_minus_B1_auc": (lambda d: roc_auc_score(d[y], d[b]) - roc_auc_score(d[y], d[a]), 0.0),
         "M_minus_B1_top10": (lambda d: top10(d, b, y) - top10(d, a, y), 0.0)}
    for name, (fn, null) in T.items():
        res = {}
        for c in ("설계", "확인1", "확인2", "최종"):
            if c == "최종" and not all(res[x]["p1"] < 0.05 and res[x]["est"] > null for x in ("확인1", "확인2")): break
            sub = S[(S["cell"] == c) & S[y].notna()]
            est = fn(sub); bs = boot(sub, fn)
            res[c] = {"est": est, "p1": float((bs <= null).mean()), "n": len(sub), "events": int(sub[y].sum()), "base": sub[y].mean(),
                      "top10_B1": top10(sub, a, y), "top10_M": top10(sub, b, y)}
        for c, r in res.items():
            res_rows.append({"target": y, "test": name, "cell": c, **r})
            logs.append([f"T8{os.environ.get('TAG', '')}-{y}-{name}-{c}", today, 8, "배당 증액·삭감 예측", "DIV", name, y, c, r["n"], name,
                         round(r["est"], 5), round(null, 3), "", round(r["p1"], 4), f"events={r['events']}"])
with open(os.path.join(ROOT, "log.csv"), "a") as fh:
    for l in logs: fh.write(",".join(str(x) for x in l) + "\n")
R = pd.DataFrame(res_rows); R.to_csv(os.path.join(OUT, "results.csv"), index=False)
json.dump(models, open(os.path.join(OUT, "models.json"), "w"), indent=1, ensure_ascii=False)
S.to_csv(os.path.join(DATA, "task8_samples" + os.environ.get("TAG", "") + ".csv"), index=False)
pd.set_option("display.width", 220, "display.float_format", "{:.4f}".format)
print(R.to_string(index=False)); print(json.dumps({k: {kk: (None if vv is None else {x: round(z, 3) for x, z in vv.items()}) if kk != "base_design" else vv for kk, vv in v.items()} for k, v in models.items()}, ensure_ascii=False))
