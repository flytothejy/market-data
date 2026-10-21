"""내부자 거래 과거분 — SEC Insider Transactions Data Sets (분기 zip, 2006~)

  python -m hub run insider_hist          빠진 분기만 받음 (처음이면 2010년부터, 주간 묶음에서 새 분기 확인)
  python -m hub run insider_hist --full   2010년부터 다시

저장: data/hub/sec/insider_hist.parquet   cik, filed, date, code(P 매수·S 매도), owner, shares, price, value
      data/hub/sec/insider_hist_done.parquet  받은 분기 목록
임원·이사의 장내 매수·매도(Form 4 거래 코드 P·S)만. 최근 며칠분은 sec_insider(공시 원문)가 더 빠름 — 이건 트레일·검증용 긴 이력
"""
import io, zipfile, datetime as dt
import pandas as pd

from .core import DATA, Run, log, sec_http, read, upsert, write
from . import universe

P = DATA / "sec" / "insider_hist.parquet"
DONE = DATA / "sec" / "insider_hist_done.parquet"
START = 2010
SEGS = ("structureddata", "datastandardsinnovation")


def quarter_rows(z, ciks):
    rd = lambda n, cols: pd.read_csv(z.open(n), sep="\t", dtype=str, usecols=cols, quoting=3, on_bad_lines="skip")
    sub = rd("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"])
    sub = sub[sub.DOCUMENT_TYPE.isin(["4", "4/A"]) & pd.to_numeric(sub.ISSUERCIK, errors="coerce").isin(ciks)]
    own = rd("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"])
    own = own[own.RPTOWNER_RELATIONSHIP.fillna("").str.contains("Officer|Director")].drop_duplicates("ACCESSION_NUMBER")
    tr = rd("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"])
    tr = tr[tr.TRANS_CODE.isin(["P", "S"])]
    m = tr.merge(sub, on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER")
    sh, px = pd.to_numeric(m.TRANS_SHARES, errors="coerce"), pd.to_numeric(m.TRANS_PRICEPERSHARE, errors="coerce")
    out = pd.DataFrame({"accession": m.ACCESSION_NUMBER, "cik": m.ISSUERCIK.astype(int),
                        "filed": pd.to_datetime(m.FILING_DATE, format="%d-%b-%Y", errors="coerce"),
                        "date": pd.to_datetime(m.TRANS_DATE, format="%d-%b-%Y", errors="coerce"), "code": m.TRANS_CODE,
                        "owner": m.RPTOWNERCIK, "shares": sh, "price": px, "value": sh * px})
    out = out.dropna(subset=["filed", "date", "value"])
    out["seq"] = out.groupby("accession").cumcount()        # 한 공시 안 여러 거래 구분용
    return out


def run(limit=0, full=False, **_):
    R = Run("insider_hist")
    http = sec_http()
    http.timeout = 180                                   # 분기 zip은 수십 MB
    ciks = set(universe.load("stock").cik.dropna().astype(int))
    done = set() if full or not DONE.exists() else set(read(DONE).q)
    today = dt.date.today()
    qs = [f"{y}q{q}" for y in range(START, today.year + 1) for q in range(1, 5) if (y, q) <= (today.year, (today.month - 1) // 3 + 1)]
    # 최근 2개 분기는 SEC가 다시 올리기도 하니 매번 다시 확인
    todo = [q for q in qs if q not in done or q in qs[-2:]]
    if limit:
        todo = todo[-limit:]
    log(f"내부자 과거분: {len(todo)}개 분기 확인")
    frames, got, missing = [], [], []
    for q in todo:
        r = None
        for seg in SEGS:
            r = http.get(f"https://www.sec.gov/files/{seg}/data/insider-transactions-data-sets/{q}_form345.zip", ok404=True)
            if r is not None:
                break
        if r is None:
            missing.append(q)
            continue
        try:
            f = quarter_rows(zipfile.ZipFile(io.BytesIO(r.content)), ciks)
        except Exception as e:
            R.warning(f"{q} 읽기 실패: {str(e)[:80]}")
            continue
        frames.append(f); got.append(q)
        log(f"  {q}: {len(f):,}건")
    if frames:
        upsert(P, pd.concat(frames, ignore_index=True), ["accession", "seq"])
        upsert(DONE, pd.DataFrame({"q": got, "fetched": pd.Timestamp.now().normalize()}), ["q"])
    # 아직 안 나온 마지막 분기는 정상 (SEC는 분기 끝나고 몇 주 뒤 게시)
    real_missing = [q for q in missing if q not in qs[-1:]]
    if real_missing:
        R.warning(f"받지 못한 분기: {', '.join(real_missing[:10])}")
    A = read(P)
    R.set(quarters_fetched=len(got), rows=len(A), companies=int(A.cik.nunique()) if len(A) else 0,
          first=str(A.date.min().date()) if len(A) else "", last_filed=str(A.filed.max().date()) if len(A) else "",
          rows_new=sum(len(f) for f in frames), http=http.stats())
    return R.done(ok=bool(len(A)))
