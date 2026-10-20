"""10-K 변화 — 새로 제출된 10-K를 직전 연도 10-K와 비교 (Actions에서 매일, 새 건만)

새 10-K가 올라오면 그 문서와 직전 연도(9~15개월 전) 10-K를 SEC에서 받아 비교하고 원문은 버림
  결과: data/hub/sec/tenk_features.parquet  문서별 유사도(본문·위험요인·경영진 논의), 새 위험 문장 비율,
                                           경영진 논의의 부정·긍정·불확실성 단어 비율, 소송 단어 비율, 포그 지수
        data/hub/sec/tenk_newsents.parquet  새로 들어온 위험 문장 원문 (문서당 최대 40개, 화면 표시용)
필요한 참고 파일 (R2, 저장소에는 올리지 않음)
  ref/LM.csv           Loughran-McDonald 금융 감성 사전 (학술용 무료 — 상업 이용 전 라이선스 확인 필요)
  sec/tenk_idf.json    단어 가중치 (PC 보관소 표본 2,000건으로 만든 것)
처음 한 번: PC 연구 자료에서 만든 과거 결과(ref/text_features.csv, ref/tenk_newsents_backfill.jsonl.gz)를 옮겨 담음
"""
import gzip, json, math, datetime as dt
import pandas as pd

from .core import DATA, Run, log, read, upsert, write, sec_http
from . import universe, tenk_text as TT

S_DIR = DATA / "sec"
REF = DATA / "ref"
FORMS = {"10-K", "10-K405", "10-KT"}
FEAT = S_DIR / "tenk_features.parquet"
SENTS = S_DIR / "tenk_newsents.parquet"


def _clean(row):
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}


def import_backfill(R, tickers):
    """PC 연구 자료에서 만든 과거 결과를 한 번만 옮겨 담음 (표시: ref/.imported)"""
    flag = REF / ".imported"
    if flag.exists():
        return 0, 0
    n1 = n2 = 0
    p = REF / "text_features.csv"
    if p.exists():
        d = pd.read_csv(p, dtype={"filed": str, "prev_filed": str, "report": str})
        d = d[d.ticker.isin(tickers)]
        upsert(FEAT, d, ["acc"], sort=["filed", "acc"])
        n1 = len(d)
    p = REF / "tenk_newsents_backfill.jsonl.gz"
    if p.exists():
        rows = [json.loads(l) for l in gzip.open(p, "rt", encoding="utf-8")]
        S = pd.DataFrame(rows)
        if not S.empty:
            S = S[S.ticker.isin(tickers)]
            old = read(SENTS)
            if not old.empty:
                S = pd.concat([S[~S.acc.isin(old.acc)], old], ignore_index=True)
            write(SENTS, S)
            n2 = S.acc.nunique()
    if n1 or n2:
        flag.write_text(dt.datetime.utcnow().isoformat())
    return n1, n2


def fetch(http, r):
    acc = r.accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{acc}/{r.doc}"
    raw = http.get(url).content.decode("utf-8", errors="ignore")
    d = TT.parse(raw)
    d.update(filed=str(pd.Timestamp(r.filed).date()), acc=r.accession, form=r.form,
             report=str(pd.Timestamp(r.report_date).date()) if pd.notna(r.report_date) else "")
    return d


def run(limit=0, full=False, days=None, **_):
    R = Run("tenk")
    lm, idf_p = REF / "LM.csv", S_DIR / "tenk_idf.json"
    if not lm.exists() or not idf_p.exists():
        R.warning(f"치명: 참고 파일 없음 — {'ref/LM.csv ' if not lm.exists() else ''}{'sec/tenk_idf.json' if not idf_p.exists() else ''}"
                  " (PC에서 python -m hub sync push --only ref/ sec/tenk_idf.json)")
        return R.done(ok=False)
    TT.init(json.loads(idf_p.read_text()), lm)
    U = universe.load("stock")
    tickers = set(U.ticker)
    b1, b2 = import_backfill(R, tickers)

    F = read(S_DIR / "filings.parquet")
    K = F[F.form.isin(FORMS) & F.ticker.isin(tickers)].copy()
    K["filed"] = pd.to_datetime(K.filed)
    look = days or (3650 if full else 120)
    have = set(read(FEAT, columns=["acc"]).acc) if FEAT.exists() else set()
    todo = K[(K.filed >= pd.Timestamp.today() - pd.Timedelta(days=look)) & ~K.accession.isin(have)].sort_values("filed")
    # 종목마다 최신 10-K가 결과에 없으면 함께 처리 (새로 편입된 종목, 과거 결과에 빠진 종목)
    latest = K.sort_values("filed").groupby("ticker").tail(1)
    missing = latest[~latest.accession.isin(have) & (latest.filed >= pd.Timestamp.today() - pd.Timedelta(days=400))]
    todo = pd.concat([todo, missing]).drop_duplicates("accession").sort_values("filed")
    # 위험요인 구간을 못 찾았던 최신 10-K는 (제목 인식 규칙이 나아졌으니) 한 번 다시 — 시도한 건 기록해 반복하지 않음
    retry_p = S_DIR / "tenk_retry.json"
    tried = set(json.loads(retry_p.read_text())) if retry_p.exists() else set()
    if FEAT.exists():
        T0 = read(FEAT)
        lt0 = T0[T0.ticker.isin(tickers)].sort_values("filed").groupby("ticker").tail(1)
        redo_acc = set(lt0[(lt0.n_rf.fillna(0) == 0)].acc) - tried
        redo = K[K.accession.isin(redo_acc)]
        if len(redo):
            log(f"위험요인 구간을 못 찾았던 최신 10-K {len(redo)}건 다시 처리")
            todo = pd.concat([todo, redo]).drop_duplicates("accession").sort_values("filed")
            retry_p.write_text(json.dumps(sorted(tried | redo_acc)))
    if limit:
        todo = todo.tail(limit)
    log(f"10-K 처리 대상 {len(todo)}건 (최근 {look}일 신규 + 결과 없는 최신분)")

    http = sec_http()
    rows, sents, fail, nprev = [], [], [], 0
    for r in todo.itertuples():
        try:
            doc = fetch(http, r)
            p = K[(K.ticker == r.ticker) & (K.filed < r.filed - pd.Timedelta(days=270)) & (K.filed > r.filed - pd.Timedelta(days=460))]
            prev = fetch(http, p.sort_values("filed").iloc[-1]) if not p.empty else None
            nprev += prev is not None
            row = TT.features(doc, prev)
            row["ticker"] = r.ticker
            rows.append(_clean(row))
            if prev is not None:
                for k, s in enumerate(TT.new_sentences(doc["rf"], prev["rf"])):
                    sents.append({"ticker": r.ticker, "acc": doc["acc"], "filed": doc["filed"], "prev_acc": prev["acc"], "rank": k, "sentence": s})
            if not doc["rf"]:
                R.warning(f"{r.ticker} {doc['filed']}: 위험요인(Item 1A) 구간을 찾지 못함")
        except Exception as e:
            fail.append(f"{r.ticker}: {str(e)[:50]}")
    if rows:
        upsert(FEAT, pd.DataFrame(rows), ["acc"], sort=["filed", "acc"])
    if sents:
        S = pd.DataFrame(sents)
        old = read(SENTS)
        if not old.empty:
            S = pd.concat([old[~old.acc.isin(S.acc)], S], ignore_index=True)
        write(SENTS, S)
    if fail:
        R.warning(f"실패 {len(fail)}건 — 예: {'; '.join(fail[:3])}")
    T = read(FEAT)
    lt = T[T.ticker.isin(tickers)].sort_values("filed").groupby("ticker").tail(1) if not T.empty else T
    R.set(processed=len(rows), with_prev=nprev, failed=len(fail), new_sentence_docs=len({x["acc"] for x in sents}),
          coverage=f"{len(lt)}/{len(tickers)}", rf_new_coverage=int(lt.rf_new.notna().sum()) if len(lt) else 0,
          backfill_rows=b1, backfill_sent_docs=b2, rows_new=len(rows), http=http.stats())
    if len(lt) and "rf_new" in lt:
        recent = lt[pd.to_datetime(lt.filed) >= pd.Timestamp.today() - pd.Timedelta(days=30)]
        if len(recent):
            R.set(top_rf_new_30d=", ".join(f"{r.ticker} {r.rf_new*100:.0f}%" for r in recent.nlargest(5, "rf_new").itertuples() if r.rf_new == r.rf_new))
    return R.done(ok=len(fail) <= max(3, len(todo) // 5))
