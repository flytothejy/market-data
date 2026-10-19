"""10-K 변화 (PC 전용, 반자동) — 새로 제출된 10-K만 받아 위험요인·경영진 논의 변화를 계산

기존 PC 자료(C:\\project\\data_ext)의 수집·특성 코드를 그대로 재사용
  원문 저장: data_ext/sec/10k/{티커}/{제출일}_{접수번호}.json.gz  (기존 보관소에 이어 붙임, 저장소에는 안 올림)
  결과 저장: data/hub/sec/tenk_features.parquet  문서별 유사도·새 위험 문장 비율·불확실성 단어 비율 등
            data/hub/sec/tenk_newsents.parquet  새로 들어온 위험 문장 원문 (문서당 최대 40개, 화면 표시용)
임베딩(텍스트 경쟁사·톤)은 GPU 스크립트(emb_build.py)를 따로 돌림
위치는 환경변수 DATA_EXT 로 바꿀 수 있음 (기본: 저장소 옆 data_ext)
"""
import gzip, importlib.util, json, math, os, re, sys, glob, datetime as dt
import pandas as pd

from .core import DATA, ROOT, Run, log, read, upsert, write, sec_http
from . import universe

S_DIR = DATA / "sec"
FORMS = {"10-K", "10-K405", "10-KT"}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def new_sentences(cur_rf, prev_rf, TF, cap=40):
    """올해 위험요인 문장 중 작년 어떤 문장과도 단어 자카드 0.5 미만인 문장 (원문)"""
    from collections import Counter
    split = lambda t: [s.strip() for s in TF.SENT.split(t or "") if len(set(TF.toks(s))) >= 8]
    cur, prev = split(cur_rf), split(prev_rf)
    if not cur or not prev:
        return []
    pv = [set(TF.toks(s)) for s in prev]
    inv = {}
    for i, s in enumerate(pv):
        for w in s:
            inv.setdefault(w, []).append(i)
    out = []
    for s in cur:
        w = set(TF.toks(s))
        cnt = Counter()
        for x in w:
            for i in inv.get(x, ()):
                cnt[i] += 1
        best = max((inter / len(w | pv[i]) for i, inter in cnt.most_common(20)), default=0.0)
        if best < 0.5:
            out.append(s[:600])
    out.sort(key=len, reverse=True)
    return out[:cap]


def run(limit=0, full=False, **_):
    R = Run("tenk")
    ext = os.environ.get("DATA_EXT") or str(ROOT.parent / "data_ext")
    fk, tfp = os.path.join(ext, "fetch_10k.py"), os.path.join(ext, "text_features.py")
    if not (os.path.exists(fk) and os.path.exists(tfp) and os.path.exists(os.path.join(ext, "sec", "LM.csv"))):
        R.warning(f"치명: {ext} 에 fetch_10k.py / text_features.py / sec/LM.csv 가 없음 (PC 전용 수집기)")
        return R.done(ok=False)
    FK, TF = _load(fk, "fetch_10k_ext"), _load(tfp, "text_features_ext")
    src = os.path.join(ext, "sec", "10k")
    F = read(S_DIR / "filings.parquet")
    U = universe.load("stock")
    F = F[F.form.isin(FORMS) & F.ticker.isin(U.ticker)]
    since = pd.Timestamp.today() - pd.Timedelta(days=3650 if full else 400)
    F = F[F.filed >= since].sort_values("filed")
    have = set(os.path.basename(p).split("_", 1)[1][:-8] for p in glob.glob(os.path.join(src, "*", "*.json.gz")))
    todo = F[~F.accession.isin(have)]
    if limit:
        todo = todo.tail(limit)
    log(f"새 10-K {len(todo)}건 다운로드 (최근 {'10년' if full else '400일'} 중 보관소에 없는 것)")
    # 1) 원문 받기 — 기존 fetch_10k 의 추출 함수 사용
    http = sec_http()
    got, fail = [], []
    for r in todo.itertuples():
        acc = r.accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{acc}/{r.doc}"
        try:
            raw = http.get(url).content.decode("utf-8", errors="ignore")
            text = FK.to_text(raw) if ("<html" in raw[:5000].lower() or "<div" in raw[:20000].lower()) else raw
            rf, md = FK.section(text, FK.RF_S, FK.RF_E), FK.section(text, FK.MD_S, FK.MD_E)
            d = os.path.join(src, r.ticker)
            os.makedirs(d, exist_ok=True)
            rec = dict(ticker=r.ticker, cik=int(r.cik), form=r.form, filed=str(r.filed.date()), report=str(r.report_date.date()) if pd.notna(r.report_date) else "",
                       acc=r.accession, full=text, rf=rf, mdna=md)
            with gzip.open(os.path.join(d, f"{rec['filed']}_{r.accession}.json.gz"), "wt", encoding="utf-8") as g:
                json.dump(rec, g)
            got.append(r.ticker)
        except Exception as e:
            fail.append(f"{r.ticker}: {str(e)[:40]}")
    # 2) 특성 계산 — 바뀐 종목만 (IDF는 한 번 만들어 저장)
    idf_p = S_DIR / "tenk_idf.json"
    if idf_p.exists():
        idf = json.loads(idf_p.read_text())
    else:
        log("IDF 계산 (표본 2,000건, 처음 한 번)")
        TF.SRC = src
        idf = TF.build_idf(sorted(os.listdir(src)))
        idf_p.parent.mkdir(parents=True, exist_ok=True)
        idf_p.write_text(json.dumps(idf))
    TF.SRC = src
    TF.init(idf)
    targets = sorted(set(got)) if not full else sorted(set(F.ticker) & set(os.listdir(src)))
    rows, sents = [], []
    for t in targets:
        for row in TF.process_ticker(t):
            rows.append(row)
        # 최신 문서의 새 위험 문장 원문
        docs = sorted(glob.glob(os.path.join(src, t, "*.json.gz")))
        if len(docs) >= 2:
            cur, prev = (json.load(gzip.open(p, "rt", encoding="utf-8")) for p in docs[-2:][::-1])
            for k, s in enumerate(new_sentences(cur.get("rf"), prev.get("rf"), TF)):
                sents.append({"ticker": t, "acc": cur["acc"], "filed": cur["filed"], "prev_acc": prev["acc"], "rank": k, "sentence": s})
    if rows:
        upsert(S_DIR / "tenk_features.parquet", pd.DataFrame(rows), ["acc"], sort=["filed", "acc"])
    if sents:
        S = pd.DataFrame(sents)
        old = read(S_DIR / "tenk_newsents.parquet")
        if not old.empty:
            old = old[~old.acc.isin(S.acc)]
            S = pd.concat([old, S], ignore_index=True)
        write(S_DIR / "tenk_newsents.parquet", S)
    if fail:
        R.warning(f"다운로드 실패 {len(fail)}건 — 예: {fail[0]}")
    T = read(S_DIR / "tenk_features.parquet")
    R.set(new_10k=len(got), failed=len(fail), recomputed_tickers=len(targets), feature_rows_total=len(T),
          new_sentence_docs=len(set(x["acc"] for x in sents)), rows_new=len(got), http=http.stats())
    if not T.empty and "rf_new" in T:
        lt = T.sort_values("filed").groupby("ticker").tail(1)
        R.set(top_rf_new=", ".join(f"{r.ticker} {r.rf_new*100:.0f}%" for r in lt.nlargest(5, "rf_new").itertuples()))
    return R.done()
