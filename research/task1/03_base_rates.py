"""과제 1-03: 실적 서프라이즈 기본 비율 + 발표 반응 기준선.

규칙(결과 보기 전에 고정, 2026-10-24):
- 이벤트: 실제 EPS·예상 EPS 둘 다 있는 과거 발표. 같은 종목·같은 날 중복은 1건으로.
- 분류: 차이 = round(실제,2) - round(예상,2). +0.01 이상 상회 / 0 부합 / -0.01 이하 하회.
- 서프라이즈 크기 = (실제-예상)/|예상|, |예상|<0.05 이면 크기 계산 제외(분모 폭주 방지).
- 반응일: 뉴욕 시각 09:30 이전 발표 → 당일, 16:00 이후 → 다음 거래일,
  장중/00:00 등 시각 불명 → '불명'으로 따로 집계(반응 분석에서 제외).
- 반응 = 반응일 종가 / 직전 거래일 종가 - 1 (수정주가). 초과반응 = 반응 - SPY 같은 날.
- 국면: 발표 직전 거래일 SPY 종가가 200일 이평 위 = 상승, 아래 = 하락.
- 4칸 분할: 종목 A/B = 시가총액 10분위 안에서 고정 시드(20261024) 무작위 배정,
  홀/짝 해 = 반응일 연도, 연말연초 경계 ±10거래일(총 20일) 이벤트는 분할표에서 제외.
"""
import os, json
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "task1", "out")
os.makedirs(OUT, exist_ok=True)

uni = pd.read_csv(os.path.join(DATA, "universe.csv"))
er = pd.read_csv(os.path.join(DATA, "earnings_raw.csv"))

# --- 정리 ---
er["dt"] = pd.to_datetime(er["dt"])
er = er[er["eps_est"].notna() & er["eps_act"].notna()].copy()
er["date"] = er["dt"].dt.normalize()
er = er.sort_values(["t", "date"]).drop_duplicates(["t", "date"], keep="first")
mins = er["dt"].dt.hour * 60 + er["dt"].dt.minute
er["timing_yf"] = np.select([(mins > 0) & (mins < 570), mins >= 960], ["BMO", "AMC"], "UNK")

# --- 8-K 항목 2.02 접수 시각으로 교차 확인 (PLAN §1: 어긋나면 8-K 우선) ---
fp = os.path.join(DATA, "raw", "r2", "sec__filings.parquet")
k8 = pd.read_parquet(fp, columns=["ticker", "form", "items", "accepted"])
k8 = k8[(k8["form"] == "8-K") & k8["items"].fillna("").str.contains("2.02")].dropna(subset=["accepted"])
k8["acc"] = pd.to_datetime(k8["accepted"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
k8["kdate"] = k8["acc"].dt.normalize()
km = k8["acc"].dt.hour * 60 + k8["acc"].dt.minute
k8["timing_8k"] = np.select([km < 570, km >= 960], ["BMO", "AMC"], "INTRA")
k8 = k8.sort_values("kdate")[["ticker", "kdate", "timing_8k"]].rename(columns={"ticker": "t"})
er = er.sort_values("date")
er = pd.merge_asof(er, k8, left_on="date", right_on="kdate", by="t",
                   direction="nearest", tolerance=pd.Timedelta(days=3))
# 8-K 날짜가 다르면 8-K 날짜를 발표일로 (장후 발표가 다음 날짜로 잡히는 경우 등)
has8 = er["kdate"].notna() & (er["timing_8k"] != "INTRA")
er.loc[has8, "date"] = er.loc[has8, "kdate"]
er["timing"] = np.where(has8, er["timing_8k"], er["timing_yf"])
# 장중 접수 8-K(은행 등: 07시 보도자료 뒤 오전에 8-K 접수)는 발표 시각 근거가 못 됨 → yfinance 시각 사용.
# yfinance 시각도 없으면 UNK (np.where 결과 그대로).
er["timing_src"] = np.select([has8, er["timing_yf"] != "UNK"], ["8k", "yf"], "none")
er = er.sort_values(["t", "date"]).drop_duplicates(["t", "date"], keep="first").reset_index(drop=True)
both = er["kdate"].notna() & (er["timing_yf"] != "UNK") & (er["timing_8k"] != "INTRA")
print("timing agree (yf vs 8k, both known):", round((er.loc[both, "timing_yf"] == er.loc[both, "timing_8k"]).mean(), 3),
      "n", int(both.sum()))

d = (er["eps_act"].round(2) - er["eps_est"].round(2)).round(2)
er["cls"] = np.select([d >= 0.01, d <= -0.01], ["beat", "miss"], "meet")
er["surp"] = np.where(er["eps_est"].abs() >= 0.05,
                      (er["eps_act"] - er["eps_est"]) / er["eps_est"].abs(), np.nan)

# --- 가격 ---
def load_px(t):
    p = os.path.join(DATA, "prices", f"{t}.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else None

spy = load_px("SPY")
spy["ret"] = spy["Close"].pct_change()
spy["ma200"] = spy["Close"].rolling(200).mean()
cal = spy.index

recs = []
for t, g in er.groupby("t"):
    px = load_px(t)
    if px is None or len(px) < 30:
        continue
    px = px.reindex(cal)
    ret = px["Close"].pct_change(fill_method=None)
    for _, r in g.iterrows():
        if r["timing"] == "UNK":
            recs.append((r.name, pd.NaT, np.nan, np.nan, None)); continue
        pos = cal.searchsorted(r["date"])  # 발표일 이상 첫 거래일
        if r["timing"] == "AMC":
            pos = pos + 1 if (pos < len(cal) and cal[pos] == r["date"]) else pos
        if pos <= 0 or pos >= len(cal):
            recs.append((r.name, pd.NaT, np.nan, np.nan, None)); continue
        rd = cal[pos]
        rr = ret.iloc[pos]
        ab = rr - spy["ret"].iloc[pos] if pd.notna(rr) else np.nan
        prev = spy.iloc[pos - 1]
        reg = None if pd.isna(prev["ma200"]) else ("up" if prev["Close"] > prev["ma200"] else "down")
        recs.append((r.name, rd, rr, ab, reg))

rx = pd.DataFrame(recs, columns=["idx", "rday", "ret", "abret", "regime"]).set_index("idx")
ev = er.join(rx)
ev = ev.merge(uni[["t", "sec", "mcap", "idx"]], on="t", how="left")
ev["sp500"] = ev["idx"].fillna("").str.contains("S&P500")
ev["year"] = ev["rday"].dt.year.fillna(ev["date"].dt.year).astype(int)

# --- 4칸 분할 배정 ---
rng = np.random.default_rng(20261024)
uni = uni.sort_values("mcap", ascending=False).reset_index(drop=True)
uni["dec"] = pd.qcut(uni["mcap"].rank(method="first"), 10, labels=False)
grp = {}
for _, g in uni.groupby("dec"):
    ts = list(g["t"]); rng.shuffle(ts)
    for i, t in enumerate(ts):
        grp[t] = "A" if i % 2 == 0 else "B"
ev["grp"] = ev["t"].map(grp)
# 경계: 반응일(없으면 발표일) 기준 연말·연초 각 10거래일
ref = ev["rday"].fillna(ev["date"])
yr_first = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[:10].max())
yr_last = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[-10:].min())
y = ref.dt.year
ev["boundary"] = (ref <= y.map(yr_first)) | (ref >= y.map(yr_last))
ev["parity"] = np.where(ev["year"] % 2 == 1, "odd", "even")
cellname = {("A", "odd"): "설계", ("A", "even"): "확인1", ("B", "odd"): "확인2", ("B", "even"): "최종"}
ev["cell"] = [cellname.get((g_, p_)) if not b_ else None
              for g_, p_, b_ in zip(ev["grp"], ev["parity"], ev["boundary"])]

ev.to_csv(os.path.join(DATA, "events.csv"), index=False)
pd.Series(grp).rename("grp").to_csv(os.path.join(DATA, "split_groups.csv"), index_label="t")

# --- 요약 ---
def summ(df):
    n = len(df)
    s = df["surp"].dropna()
    a = df["abret"].dropna()
    out = {
        "n": n,
        "beat": (df["cls"] == "beat").mean(), "meet": (df["cls"] == "meet").mean(),
        "miss": (df["cls"] == "miss").mean(),
        "surp_med": s.median(), "surp_p25": s.quantile(.25), "surp_p75": s.quantile(.75),
        "n_react": len(a),
        "ab_mean": a.mean(), "ab_up": (a > 0).mean(), "ab_absmed": a.abs().median(),
    }
    for c in ["beat", "meet", "miss"]:
        ac = df.loc[df["cls"] == c, "abret"].dropna()
        out[f"ab_mean_{c}"] = ac.mean()
        out[f"ab_up_{c}"] = (ac > 0).mean() if len(ac) else np.nan
    return pd.Series(out)

tables = {}
tables["overall"] = summ(ev).to_frame("전체").T
tables["timing"] = ev.groupby("timing").apply(summ, include_groups=False)
tables["timing_src"] = ev.groupby("timing_src").apply(summ, include_groups=False)
tables["year"] = ev.groupby("year").apply(summ, include_groups=False)
tables["sp500"] = ev.groupby("sp500").apply(summ, include_groups=False)
tables["sector"] = ev.groupby("sec").apply(summ, include_groups=False)
tables["regime"] = ev.dropna(subset=["regime"]).groupby("regime").apply(summ, include_groups=False)
tables["cell"] = ev.dropna(subset=["cell"]).groupby("cell").apply(summ, include_groups=False)
ev["era"] = pd.cut(ev["year"], [2000, 2009, 2014, 2019, 2030], labels=["~2009", "2010-14", "2015-19", "2020~"])
tables["era"] = ev.groupby("era", observed=True).apply(summ, include_groups=False)
# 서프라이즈 크기 5분위별 반응
q = ev.dropna(subset=["surp", "abret"]).copy()
q["sq"] = pd.qcut(q["surp"], 5, labels=["Q1(최하)", "Q2", "Q3", "Q4", "Q5(최상)"])
tables["surp_quintile"] = q.groupby("sq", observed=True).agg(
    n=("abret", "size"), surp_min=("surp", "min"), surp_max=("surp", "max"),
    ab_mean=("abret", "mean"), ab_med=("abret", "median"), ab_up=("abret", lambda x: (x > 0).mean()))

with pd.ExcelWriter(os.path.join(OUT, "base_rates.xlsx")) as w:
    for k, v in tables.items():
        v.to_excel(w, sheet_name=k)
for k, v in tables.items():
    v.to_csv(os.path.join(OUT, f"base_{k}.csv"))
meta = {"events_total": int(len(ev)), "tickers": int(ev["t"].nunique()),
        "first": str(ev["date"].min().date()), "last": str(ev["date"].max().date()),
        "unk_share": float((ev["timing"] == "UNK").mean())}
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=1)
pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.3f}".format)
print(meta)
for k in ["overall", "timing", "era", "sp500", "regime", "cell", "surp_quintile"]:
    print("\n==", k); print(tables[k])
