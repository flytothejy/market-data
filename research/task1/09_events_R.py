"""과제 1-09: 재검증 1R 이벤트 (PLAN §8). 지금 유니버스 이벤트 + 상장폐지 회사의 8-K 2.02 이벤트.
출력: research/data/events_R.csv
"""
import os, json, time, hashlib
import numpy as np, pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); SB = os.path.join(DATA, "raw", "sb"); CF = os.path.join(SB, "companyfacts")
PX = os.path.join(DATA, "prices"); PXD = os.path.join(DATA, "prices_delisted")
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}
S = requests.Session(); S.headers.update(H)

spy = pd.read_parquet(os.path.join(PX, "SPY.parquet"))["Close"]; cal = spy.index
spy_ret = spy.pct_change(); ma200 = spy.rolling(200).mean()

# ---------- 상장폐지 회사 8-K 2.02 ----------
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv"))
dm = dm[dm["status"].isin(["unique", "still_filing_other_ticker"])].copy()
dm["cik"] = dm["cik"].astype(int)
rows = []
for r in dm.itertuples():
    p = os.path.join(CF, f"{r.cik}_sub.json")
    if not os.path.exists(p): continue
    j = json.load(open(p))
    parts = [j.get("filings", {}).get("recent", {})]
    for fobj in j.get("filings", {}).get("files", []):
        fp = os.path.join(CF, f"{r.cik}_{fobj['name']}")
        if not os.path.exists(fp):
            for a in range(3):
                rr = S.get(f"https://data.sec.gov/submissions/{fobj['name']}", timeout=60)
                if rr.status_code == 200: open(fp, "w").write(rr.text); break
                time.sleep(2 + 3 * a)
            time.sleep(0.12)
        try: parts.append(json.load(open(fp)))
        except Exception: pass
    for pt in parts:
        if not pt: continue
        for f, it, acc in zip(pt.get("form", []), pt.get("items", [""] * len(pt.get("form", []))), pt.get("acceptanceDateTime", [])):
            if f == "8-K" and "2.02" in [x.strip() for x in (it or "").split(",")] and acc:
                rows.append((r.code, r.cik, acc))
d8 = pd.DataFrame(rows, columns=["code", "cik", "acc"]).drop_duplicates()
d8["acc"] = pd.to_datetime(d8["acc"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
d8 = d8.sort_values(["code", "acc"])
mins = d8["acc"].dt.hour * 60 + d8["acc"].dt.minute
d8["timing"] = np.select([mins < 570, mins >= 960], ["BMO", "AMC"], "INTRA")
keep, last = [], {}
for r in d8.itertuples():                                   # 45일 안 중복 2.02 버림 (INTRA 포함해서 판단)
    lt = last.get(r.code)
    if lt is not None and (r.acc - lt).days < 45: continue
    last[r.code] = r.acc; keep.append(r.Index)
d8 = d8.loc[keep]; d8 = d8[d8["timing"] != "INTRA"].copy()
d8["date"] = d8["acc"].dt.normalize()
print("delisted 2.02 events (after dedup, non-intraday):", len(d8), "companies", d8["code"].nunique())

# ---------- 가격·반응 ----------
def load(t):
    p = os.path.join(PXD, t[2:].replace("/", "_") + ".parquet") if t.startswith("D:") else os.path.join(PX, f"{t}.parquet")
    if not os.path.exists(p): return None
    x = pd.read_parquet(p)[["Close", "RawClose", "Volume"]].groupby(level=0).last()
    return x.reindex(cal)

def build(g, t):
    px = load(t)
    if px is None: return []
    ret = px["Close"].pct_change(fill_method=None)
    dv = (px["RawClose"] * px["Volume"]).rolling(252, min_periods=200).mean()
    out = []
    for r in g.itertuples():
        pos = cal.searchsorted(r.date)
        if r.timing == "AMC" and pos < len(cal) and cal[pos] == r.date: pos += 1
        if pos <= 0 or pos >= len(cal): continue
        rr = ret.iloc[pos]
        if rr != rr: continue
        prev = pos - 1
        reg = None if ma200.iloc[prev] != ma200.iloc[prev] else ("up" if spy.iloc[prev] > ma200.iloc[prev] else "down")
        out.append({"t": t, "date": r.date, "rday": cal[pos], "timing": r.timing, "ret": rr, "abret": rr - spy_ret.iloc[pos],
                    "dv252": dv.iloc[prev], "regime": reg, "src": getattr(r, "src", "cur")})
    return out

ev = pd.read_csv(os.path.join(DATA, "events.csv"), parse_dates=["date", "rday"])
ev = ev[ev["rday"].notna() & ev["abret"].notna()]
recs = []
for t, g in ev.groupby("t"):
    recs += build(g.assign(src="cur"), t.replace(".", "-"))
for c, g in d8.groupby("code"):
    recs += build(g.assign(src="delisted"), "D:" + c)
E = pd.DataFrame(recs)
E = E[(E["rday"] >= "2005-01-01") & (E["dv252"] >= 20e6)].copy()

# ---------- 4칸 ----------
grp = pd.read_csv(os.path.join(DATA, "split_groups.csv"))
grp["t"] = grp["t"].str.replace(".", "-", regex=False); grp = grp.set_index("t")["grp"]
E["grp"] = [grp.get(t) if not t.startswith("D:") else ("A" if hashlib.md5(t[2:].encode()).digest()[0] % 2 == 0 else "B") for t in E["t"]]
y = E["rday"].dt.year
yf_ = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[:10].max()); yl_ = pd.Series(cal).groupby(cal.year).apply(lambda s: s.iloc[-10:].min())
E["boundary"] = (E["rday"] <= y.map(yf_)) | (E["rday"] >= y.map(yl_))
names = {("A", 1): "설계", ("A", 0): "확인1", ("B", 1): "확인2", ("B", 0): "최종"}
E["cell"] = [None if b or g_ is None else names[(g_, yy % 2)] for g_, yy, b in zip(E["grp"], y, E["boundary"])]
E["year"] = y
E.to_csv(os.path.join(DATA, "events_R.csv"), index=False)
print(E.groupby("src").size().to_dict(), "| by cell:", E["cell"].value_counts().to_dict())
print(E.groupby([E["year"] // 5 * 5, "src"]).size().unstack().to_string())
