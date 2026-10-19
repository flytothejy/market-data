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


API = "https://apis.data.go.kr/1160100/GetSecuritiesProductInfoService_V2/getETFPriceInfo_V2"


def run_api(R, key, limit=0, days=None, full=False):
    """공공데이터포털 '금융위원회_증권상품시세정보' (전 영업일 기준, 하루 늦게 갱신)"""
    import os
    from .core import Http
    http = Http(rate=5)
    have = sorted((K_DIR / "daily").glob("*.parquet"))
    span = days or (730 if full or not have else 14)
    end = dt.date.today()
    dates = [end - dt.timedelta(days=k) for k in range(span, -1, -1)]
    dates = [d for d in dates if d.weekday() < 5]
    if limit:
        dates = dates[-limit:]
    rows, empty = [], 0
    for d in dates:
        page = 1
        while True:
            r = http.get(API, params={"serviceKey": key, "resultType": "json", "numOfRows": 1000, "pageNo": page,
                                      "basDt": d.strftime("%Y%m%d")})
            try:
                body = r.json()["response"]["body"]
            except Exception:
                raise RuntimeError(f"API 응답 해석 실패: {r.text[:200]}")
            items = (body.get("items") or {}).get("item") or []
            if isinstance(items, dict):
                items = [items]
            rows += items
            if page * 1000 >= int(body.get("totalCount") or 0):
                break
            page += 1
        if not items and page == 1:
            empty += 1
    if not rows:
        R.warning("치명: API에서 받은 행이 없음 (키 승인 대기·일일 한도·휴장 확인)")
        return R.done(ok=False)
    A = pd.DataFrame(rows)
    num = ["clpr", "nav", "trqu", "trPrc", "mrktTotAmt", "nPptTotAmt", "stLstgCnt", "bssIdxClpr", "fltRt"]
    for c in num:
        if c in A:
            A[c] = pd.to_numeric(A[c], errors="coerce")
    A = A.rename(columns={"basDt": "date", "srtnCd": "code", "itmsNm": "name", "clpr": "close", "trqu": "volume", "trPrc": "value",
                          "mrktTotAmt": "mktcap", "nPptTotAmt": "net_assets", "bssIdxIdxNm": "index_name", "bssIdxClpr": "index_close"})
    A["date"] = pd.to_datetime(A["date"], format="%Y%m%d")
    us = A["name"].astype(str).str.contains(US_KEYS) | A.get("index_name", pd.Series("", index=A.index)).astype(str).str.contains(r"S&P|NASDAQ|Nasdaq|Dow|NYSE|PHLX|US")
    A = A[us & ~A["name"].astype(str).str.contains(EXCLUDE)].copy()
    A["deviation"] = (A["close"] / A["nav"] - 1) * 100
    keep = [c for c in ["date", "code", "name", "close", "nav", "volume", "value", "mktcap", "net_assets", "index_name", "index_close", "deviation"] if c in A]
    A = A[keep]
    for y, g in A.groupby(A.date.dt.year):
        upsert(K_DIR / "daily" / f"{y}.parquet", g, ["date", "code"])
    L = A.sort_values("date").groupby("code").last().reset_index()[["code", "name"] + (["index_name"] if "index_name" in A else [])]
    L["group"] = L["name"].map(classify)
    write(K_DIR / "list.parquet", L)
    # 추적오차: NAV 수익률 - 기초지수 수익률의 연환산 표준편차 (최근 1년, 원화 환산 차이 포함 주의)
    allA = pd.concat([read(p) for p in sorted((K_DIR / "daily").glob("*.parquet"))], ignore_index=True).sort_values(["code", "date"])
    allA["d"] = allA.groupby("code").nav.pct_change() - allA.groupby("code").index_close.pct_change()
    te = allA[allA.date >= allA.date.max() - pd.Timedelta(days=365)].groupby("code").d.std() * (252 ** 0.5) * 100
    R.set(data_source="공공데이터포털", days_fetched=len(dates) - empty, us_equity_etf=len(L), rows_new=len(A),
          first=str(A.date.min().date()), latest=str(A.date.max().date()),
          nav_coverage=f"{A.nav.notna().mean()*100:.0f}%", median_deviation=f"{A.deviation.abs().median():.2f}%",
          median_tracking_diff=f"{te.median():.1f}%p" if len(te) else "-",
          groups=", ".join(f"{k} {v}" for k, v in L.group.value_counts().items()), http=http.stats())
    return R.done()


def run(limit=0, days=None, full=False, **_):
    R = Run("kr_etf")
    import os
    from .core import data_go_kr_key
    key = data_go_kr_key("etf")
    if key:
        return run_api(R, key, limit, days, full)
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
        import pykrx
        R.set(pykrx_version=getattr(pykrx, "__version__", "?"))
        R.warning("치명: 한국거래소 ETF 목록을 받지 못함 — 공공데이터포털 API 키를 환경변수 DATA_GO_KR_KEY로 설정하면 그쪽으로 받습니다")
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
