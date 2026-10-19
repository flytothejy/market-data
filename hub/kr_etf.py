"""국내 상장 미국 ETF — 가격·NAV·괴리율·추적오차·구성(PDF) — 한국거래소 데이터(pykrx)

처음 실행은 '접속 시험'을 겸함: 한국거래소가 막히면 무엇이 안 되는지 점검표에 그대로 표시
저장
  data/hub/kr_etf/list.parquet          종목코드, 이름, 추종 대상(이름 기준 분류)
  data/hub/kr_etf/daily/YYYY.parquet    date, code, close, nav, volume, value, deviation, tracking_error
  data/hub/kr_etf/pdf/YYYY-MM-DD.parquet  code, holding, name, shares, weight
"""
import datetime as dt, time, re
import pandas as pd

from .core import DATA, Run, log, read, upsert, write

K_DIR = DATA / "kr_etf"
US_KEYS = re.compile(r"미국|나스닥|S&P|다우|필라델피아|NYSE|테슬라|엔비디아|애플|마이크로소프트|빅테크|팡|FANG|US|글로벌반도체|美")
EXCLUDE = re.compile(r"채권|국채|달러|선물|레버리지|인버스|커버드|액티브")   # 1차 범위: 주식형·현물·패시브


def classify(name):
    for k, v in [("나스닥", "나스닥100"), ("S&P", "S&P500"), ("배당", "미국배당"), ("반도체", "반도체"), ("다우", "다우"), ("테크", "테크")]:
        if k in name:
            return v
    return "기타 미국"


def run(limit=0, days=None, full=False, **_):
    R = Run("kr_etf")
    try:
        from pykrx import stock
    except ImportError:
        R.warning("치명: pykrx가 없습니다 → pip install pykrx")
        return R.done(ok=False)
    today = dt.date.today()
    # 최근 거래일 찾기
    lst, d = [], today
    for _ in range(7):
        try:
            lst = stock.get_etf_ticker_list(d.strftime("%Y%m%d"))
        except Exception as e:
            R.warning(f"ETF 목록 실패({d}): {str(e)[:80]}")
            lst = []
        if lst:
            break
        d -= dt.timedelta(days=1)
    if not lst:
        R.warning("치명: 한국거래소 ETF 목록을 받지 못함 (접속 차단 또는 로그인 요구 가능)")
        return R.done(ok=False)
    rows = []
    for c in lst:
        try:
            n = stock.get_etf_ticker_name(c)
        except Exception:
            continue
        if US_KEYS.search(n) and not EXCLUDE.search(n):
            rows.append({"code": c, "name": n, "group": classify(n)})
    L = pd.DataFrame(rows)
    write(K_DIR / "list.parquet", L)
    R.set(etf_total=len(lst), us_equity_etf=len(L), basis_date=str(d))
    if limit:
        L = L.head(limit)
    have = sorted((K_DIR / "daily").glob("*.parquet"))
    span = days or (730 if full or not have else 10)
    f, t = (d - dt.timedelta(days=span)).strftime("%Y%m%d"), d.strftime("%Y%m%d")
    D, P, fails = [], [], {"ohlcv": 0, "deviation": 0, "tracking": 0, "pdf": 0}
    for i, r in enumerate(L.itertuples()):
        try:
            o = stock.get_etf_ohlcv_by_date(f, t, r.code)
            o = o.rename(columns={"NAV": "nav", "종가": "close", "거래량": "volume", "거래대금": "value"})
            o = o[[c for c in ["nav", "close", "volume", "value"] if c in o]]
        except Exception:
            fails["ohlcv"] += 1
            continue
        try:
            dv = stock.get_etf_price_deviation(f, t, r.code)
            o["deviation"] = dv.get("괴리율")
        except Exception:
            fails["deviation"] += 1
        try:
            te = stock.get_etf_tracking_error(f, t, r.code)
            o["tracking_error"] = te.get("추적오차율")
        except Exception:
            fails["tracking"] += 1
        o = o.reset_index().rename(columns={o.index.name or "index": "date", "날짜": "date"})
        o["code"] = r.code
        D.append(o)
        try:
            pdf = stock.get_etf_portfolio_deposit_file(r.code, t)
            if pdf is not None and len(pdf):
                pdf = pdf.reset_index()
                P.append(pd.DataFrame({"code": r.code, "holding": pdf.iloc[:, 0].astype(str),
                                       "shares": pd.to_numeric(pdf.get("계약수"), errors="coerce"),
                                       "value": pd.to_numeric(pdf.get("금액"), errors="coerce"),
                                       "weight": pd.to_numeric(pdf.get("비중"), errors="coerce")}))
        except Exception:
            fails["pdf"] += 1
        time.sleep(0.3)
        if (i + 1) % 20 == 0:
            log(f"  국내 ETF {i+1}/{len(L)}")
    if not D:
        R.warning("치명: 가격·NAV를 하나도 받지 못함")
        return R.done(ok=False)
    A = pd.concat(D, ignore_index=True)
    A["date"] = pd.to_datetime(A["date"])
    for y, g in A.groupby(A.date.dt.year):
        upsert(K_DIR / "daily" / f"{y}.parquet", g, ["date", "code"])
    if P:
        write(K_DIR / "pdf" / f"{d}.parquet", pd.concat(P, ignore_index=True))
    for k, v in fails.items():
        if v:
            R.warning(f"{k} 실패 {v}개")
    R.set(fetched=A.code.nunique(), rows_new=len(A), first=str(A.date.min().date()), latest=str(A.date.max().date()),
          nav_coverage=f"{A.nav.notna().mean()*100:.0f}%" if "nav" in A else "없음",
          pdf_etfs=len(P), groups=", ".join(f"{k} {v}" for k, v in L.group.value_counts().items()))
    return R.done()
