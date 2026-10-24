"""과제 2-02: 상장폐지 회사 10-K 지표를 티커맵 계산 코드(hub/tenk_text.py) 그대로 계산 (PLAN §6).
MODE=check : 지금 종목 10-K 20건을 다시 계산해 티커맵 값과 비교 (결과 보기 전 일치 확인)
MODE=run   : 상장폐지 회사 전체 계산 → research/data/raw/sb/tenk_delisted.csv
"""
import os, sys, json, time, gzip, threading, importlib.util
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
SB = os.path.join(ROOT, "data", "raw", "sb"); CF = os.path.join(SB, "companyfacts"); R2 = os.path.join(ROOT, "data", "raw", "r2")
DOC = os.path.join(SB, "tenk_docs"); os.makedirs(DOC, exist_ok=True)
spec = importlib.util.spec_from_file_location("tenk_text", os.path.join(REPO, "hub", "tenk_text.py"))
TT = importlib.util.module_from_spec(spec); spec.loader.exec_module(TT)
TT.init(json.load(open(os.path.join(R2, "sec__tenk_idf.json"))), os.path.join(R2, "ref__LM.csv"))
FORMS = {"10-K", "10-K405", "10-KT"}
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}
lock = threading.Lock(); last = [0.0]
S = requests.Session(); S.headers.update(H)

def get(url):
    for a in range(4):
        with lock:
            w = 0.13 - (time.time() - last[0])
            if w > 0: time.sleep(w)
            last[0] = time.time()
        try:
            r = S.get(url, timeout=90)
        except requests.RequestException:
            time.sleep(3 + 3 * a); continue
        if r.status_code == 200: return r.content.decode("utf-8", errors="ignore")
        if r.status_code == 404: return None
        time.sleep(3 + 5 * a)
    return None

def doc(cik, acc, primary):
    """문서를 받아 섹션으로 나눠 캐시 (원문은 버림)"""
    p = os.path.join(DOC, f"{acc}.json.gz")
    if os.path.exists(p):
        return json.load(gzip.open(p, "rt"))
    raw = get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{primary}")
    if raw is None:
        json.dump({}, gzip.open(p, "wt")); return {}
    d = TT.parse(raw)
    json.dump(d, gzip.open(p, "wt")); return d

def features(cik, cur, prev):
    d = doc(cik, cur["acc"], cur["primary"])
    if not d: return None
    d.update(filed=cur["filed"], acc=cur["acc"], form=cur["form"], report=cur.get("report", ""))
    pv = None
    if prev is not None:
        pd_ = doc(cik, prev["acc"], prev["primary"])
        if pd_:
            pd_.update(filed=prev["filed"], acc=prev["acc"], form=prev["form"]); pv = pd_
    return TT.features(d, pv)

def pick_prev(K, filed):
    f = pd.Timestamp(filed)
    p = K[(K["filed_ts"] < f - pd.Timedelta(days=270)) & (K["filed_ts"] > f - pd.Timedelta(days=460))]
    return None if p.empty else p.sort_values("filed_ts").iloc[-1].to_dict()

MODE = os.environ.get("MODE", "check")
if MODE == "check":
    T = pd.read_parquet(os.path.join(R2, "sec__tenk_features.parquet"))
    F = pd.read_parquet(os.path.join(R2, "sec__filings.parquet"), columns=["cik", "ticker", "accession", "form", "filed", "report_date", "doc"])
    F = F[F["form"].isin(FORMS)]
    T = T[T["prev_acc"].notna() & T["rf_new"].notna()].sample(20, random_state=7)
    rows = []
    for r in T.itertuples():
        K = F[F["ticker"] == r.ticker].copy(); K["filed_ts"] = pd.to_datetime(K["filed"])
        cur = K[K["accession"] == r.acc]
        if cur.empty: continue
        c = cur.iloc[0]
        cd = {"acc": c.accession, "primary": c.doc, "filed": str(pd.Timestamp(c.filed).date()), "form": c.form}
        pv = pick_prev(K.rename(columns={"accession": "acc", "doc": "primary"}), c.filed)
        if pv: pv["filed"] = str(pd.Timestamp(pv["filed"]).date())
        f = features(c.cik, cd, pv)
        if f: rows.append({"ticker": r.ticker, "acc": r.acc, **{f"tm_{k}": getattr(r, k) for k in ("sim_full", "sim_rf", "sim_md", "rf_new", "md_unc")},
                           **{f"me_{k}": f.get(k) for k in ("sim_full", "sim_rf", "sim_md", "rf_new", "md_unc")}})
    d = pd.DataFrame(rows); d.to_csv(os.path.join(ROOT, "task2", "out", "tenk_check.csv"), index=False)
    for k in ("sim_full", "sim_rf", "sim_md", "rf_new", "md_unc"):
        a, b = d[f"tm_{k}"].astype(float), d[f"me_{k}"].astype(float)
        print(f"{k:9s} n={a.notna().sum():2d} corr={a.corr(b):.4f} max|diff|={(a - b).abs().max():.4f}")
    sys.exit()

# ---------- 상장폐지 회사 전체 ----------
dm = pd.read_csv(os.path.join(SB, "delisted_cik.csv"))
dm = dm[dm["status"].isin(["unique", "still_filing_other_ticker"])].copy(); dm["cik"] = dm["cik"].astype(int)
jobs = []
for r in dm.drop_duplicates("cik").itertuples():
    p = os.path.join(CF, f"{r.cik}_sub.json")
    if not os.path.exists(p): continue
    j = json.load(open(p)); parts = [j.get("filings", {}).get("recent", {})]
    for fo in j.get("filings", {}).get("files", []):
        fp = os.path.join(CF, f"{r.cik}_{fo['name']}")
        if os.path.exists(fp):
            try: parts.append(json.load(open(fp)))
            except Exception: pass
    ks = []
    for pt in parts:
        for fm, fd, ac, pr, rd in zip(pt.get("form", []), pt.get("filingDate", []), pt.get("accessionNumber", []),
                                       pt.get("primaryDocument", []), pt.get("reportDate", [""] * len(pt.get("form", [])))):
            if fm in FORMS and pr and fd >= "2005-01-01":
                ks.append({"acc": ac, "filed": fd, "form": fm, "primary": pr, "report": rd})
    if not ks: continue
    K = pd.DataFrame(ks).drop_duplicates("acc"); K["filed_ts"] = pd.to_datetime(K["filed"])
    codes = dm.loc[dm["cik"] == r.cik, "code"].tolist()
    for c in K[K["filed"] >= "2006-01-01"].to_dict("records"):
        jobs.append((r.cik, codes, c, pick_prev(K, c["filed"])))
print("delisted 10-K jobs", len(jobs), flush=True)
out = []; done = [0]
def work(job):
    cik, codes, cur, prev = job
    try:
        f = features(cik, cur, prev)
    except Exception as e:
        f = None
    with lock:
        done[0] += 1
        if done[0] % 500 == 0: print(done[0], flush=True)
    if f is None: return
    for code in codes:
        out.append({"t": "D:" + code, "cik": cik, **{k: f.get(k) for k in ("filed", "acc", "form", "n_full", "n_rf", "n_md", "md_unc",
                                                                          "prev_acc", "prev_filed", "sim_full", "sim_rf", "sim_md", "rf_new")}})
with ThreadPoolExecutor(max_workers=6) as ex:
    list(ex.map(work, jobs))
o = pd.DataFrame(out)
o.to_csv(os.path.join(SB, "tenk_delisted.csv"), index=False)
print("rows", len(o), "with prev", int(o["prev_acc"].notna().sum()), "companies", o["cik"].nunique())
