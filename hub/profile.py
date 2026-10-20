"""기업·ETF 개요 + 공매도 잔고 (yfinance info) — 주 1회

저장
  data/hub/profile/profile.parquet        최신 개요 (종목당 1행)
  data/hub/profile/short_interest.parquet  공매도 잔고 이력 (잔고 기준일이 바뀔 때만 행 추가)
"""
import time, datetime as dt
import pandas as pd
import yfinance as yf

from .core import DATA, Run, log, upsert, write, read
from . import universe

D = DATA / "profile"
STOCK_F = ["shortName", "longName", "sector", "industry", "country", "website", "fullTimeEmployees", "longBusinessSummary",
           "marketCap", "sharesOutstanding", "floatShares", "heldPercentInsiders", "heldPercentInstitutions", "beta",
           "exchange", "currency", "earningsTimestampStart", "earningsTimestampEnd", "earningsTimestamp", "isEarningsDateEstimate",
           "exDividendDate", "dividendRate", "dividendYield", "payoutRatio", "fiscalYearEnd" ]
ETF_F = ["shortName", "longName", "fundFamily", "category", "legalType", "totalAssets", "netExpenseRatio", "annualReportExpenseRatio",
         "yield", "trailingAnnualDividendYield", "fundInceptionDate", "beta3Year", "ytdReturn", "threeYearAverageReturn",
         "fiveYearAverageReturn", "navPrice", "exchange", "longBusinessSummary"]
SI_F = ["sharesShort", "sharesShortPriorMonth", "dateShortInterest", "sharesShortPreviousMonthDate", "shortPercentOfFloat", "shortRatio"]


def run(limit=0, **_):
    R = Run("profile")
    U = universe.load()
    if limit:
        U = U.head(limit)
    rows, si, fail = [], [], []
    for i, r in enumerate(U.itertuples()):
        for attempt in range(3):
            try:
                info = yf.Ticker(r.ticker).info or {}
                break
            except Exception as e:
                info = None
                time.sleep(3 * (attempt + 1))
        if not info or len(info) < 5:
            fail.append(r.ticker)
            continue
        flds = ETF_F if r.kind == "etf" else STOCK_F
        rec = {"ticker": r.ticker, "kind": r.kind, **{k: info.get(k) for k in flds}}
        if rec.get("longBusinessSummary"):
            rec["longBusinessSummary"] = str(rec["longBusinessSummary"])[:2000]
        rows.append(rec)
        if r.kind == "stock" and info.get("sharesShort"):
            si.append({"ticker": r.ticker, **{k: info.get(k) for k in SI_F}})
        if (i + 1) % 100 == 0:
            log(f"  개요 {i+1}/{len(U)}")
        time.sleep(0.15)
    if not rows:
        R.warning("치명: 받은 개요가 없음")
        return R.done(ok=False)
    P = pd.DataFrame(rows)
    P["fetched"] = pd.Timestamp.now().normalize()
    old = read(D / "profile.parquet")
    if not old.empty:                     # 실패한 종목은 이전 값 유지
        P = pd.concat([old[~old.ticker.isin(P.ticker)], P], ignore_index=True)
    for c in P.columns:
        if P[c].dtype == object:
            num = pd.to_numeric(P[c], errors="coerce")
            P[c] = num if num.notna().sum() == P[c].notna().sum() else P[c].astype("string")
    write(D / "profile.parquet", P)
    if si:
        S = pd.DataFrame(si)
        S["date"] = pd.to_datetime(S["dateShortInterest"], unit="s", errors="coerce").dt.date.astype("string")
        # 직전 달 잔고도 한 줄로 (이미 있는 날짜는 건드리지 않음) → 첫 수집부터 두 시점
        prev = S[S.sharesShortPriorMonth.notna() & S.sharesShortPreviousMonthDate.notna()].copy()
        if len(prev):
            prev["date"] = pd.to_datetime(prev["sharesShortPreviousMonthDate"], unit="s", errors="coerce").dt.date.astype("string")
            prev["sharesShort"] = prev["sharesShortPriorMonth"]
            prev["shortPercentOfFloat"] = None
            prev["shortRatio"] = None
            old = read(D / "short_interest.parquet")
            if not old.empty:
                prev = prev[~(prev.ticker + "|" + prev.date).isin(set(old.ticker + "|" + old.date.astype(str)))]
            S = pd.concat([prev, S], ignore_index=True)
        upsert(D / "short_interest.parquet", S, ["ticker", "date"])
    if fail:
        R.warning(f"실패 {len(fail)}개: {', '.join(fail[:15])}")
    st = P[P.kind == "stock"]
    R.set(fetched=len(rows), failed=len(fail), rows_new=len(rows),
          sector_coverage=f"{st.sector.notna().mean()*100:.0f}%",
          short_interest=f"{len(si)}종목" + (f" · 기준일 {pd.to_datetime(max(x['dateShortInterest'] or 0 for x in si), unit='s').date()}" if si else ""),
          etf_expense_coverage=f"{P[P.kind=='etf'][['netExpenseRatio','annualReportExpenseRatio']].notna().any(axis=1).mean()*100:.0f}%" if (P.kind == "etf").any() else "-")
    return R.done()
