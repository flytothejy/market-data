"""일별 가격(시·고·저·종·수정종가·거래량) + 배당·분할 — yfinance 일괄 다운로드

저장
  data/hub/prices/daily/YYYY.parquet   date, ticker, open, high, low, close, adj_close, volume
  data/hub/prices/actions.parquet      date, ticker, dividend, split
처음 실행(또는 --full)은 2006년부터, 이후에는 최근 1개월만 받아 덮어씀(수정·배당 반영)
"""
import time
import numpy as np, pandas as pd
import yfinance as yf

from .core import DATA, Run, log, upsert, read
from . import universe

P_DIR = DATA / "prices"
START = "2006-01-01"
CHUNK = 100


def to_long(raw, tickers):
    out, acts = [], []
    if raw is None or raw.empty:
        return pd.DataFrame(), pd.DataFrame()
    single = not isinstance(raw.columns, pd.MultiIndex)
    for t in tickers:
        try:
            d = raw if single else raw[t]
        except KeyError:
            continue
        if "Close" not in d:
            continue
        d = d.dropna(subset=["Close"])
        if d.empty:
            continue
        f = pd.DataFrame({"date": d.index.tz_localize(None) if d.index.tz is not None else d.index, "ticker": t,
                          "open": d["Open"].astype("float32").values, "high": d["High"].astype("float32").values,
                          "low": d["Low"].astype("float32").values, "close": d["Close"].astype("float32").values,
                          "adj_close": d.get("Adj Close", d["Close"]).astype("float32").values,
                          "volume": d["Volume"].fillna(0).astype("int64").values})
        out.append(f)
        if "Dividends" in d or "Stock Splits" in d:
            a = pd.DataFrame({"date": f["date"].values, "ticker": t,
                              "dividend": d.get("Dividends", pd.Series(0, index=d.index)).fillna(0).values,
                              "split": d.get("Stock Splits", pd.Series(0, index=d.index)).fillna(0).values})
            acts.append(a[(a.dividend != 0) | (a.split != 0)])
    L = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    A = pd.concat(acts, ignore_index=True) if acts else pd.DataFrame()
    return L, A


def run(limit=0, full=False, **_):
    R = Run("prices")
    U = universe.load()
    tickers = list(U.ticker)
    if limit:
        tickers = tickers[:limit]
    done_p = P_DIR / "_backfilled.parquet"
    done = set(read(done_p).ticker) if done_p.exists() else set()
    new_t = tickers if full else [t for t in tickers if t not in done]
    old_t = [] if full else [t for t in tickers if t in done]
    R.set(requested=len(tickers), backfill_tickers=len(new_t), update_tickers=len(old_t))
    log(f"가격 수집: 전체 이력 {len(new_t)}종목 · 최근 1개월 {len(old_t)}종목")
    groups = [(new_t, {"start": START}), (old_t, {"period": "1mo"})]

    Ls, As, miss, n = [], [], [], 0
    for group, kw in groups:
        for i in range(0, len(group), CHUNK):
            part = group[i:i + CHUNK]
            for attempt in range(3):
                try:
                    raw = yf.download(part, auto_adjust=False, actions=True, group_by="ticker", threads=True, progress=False, **kw)
                    break
                except Exception as e:
                    log(f"  재시도 {attempt+1}: {e}")
                    time.sleep(10 * (attempt + 1))
            else:
                R.warning(f"묶음 실패: {part[0]}~")
                miss += part
                continue
            L, A = to_long(raw, part)
            got = set(L.ticker) if not L.empty else set()
            miss += [t for t in part if t not in got]
            Ls.append(L); As.append(A)
            n += len(part)
            log(f"  {n}/{len(tickers)} · 행 {len(L):,}")
            if "start" in kw and got:
                upsert(done_p, pd.DataFrame({"ticker": sorted(got)}), ["ticker"])
    L = pd.concat(Ls, ignore_index=True) if Ls else pd.DataFrame()
    A = pd.concat(As, ignore_index=True) if As else pd.DataFrame()
    if L.empty:
        R.warning("치명: 받은 가격이 없음")
        return R.done(ok=False)

    for y, g in L.groupby(L.date.dt.year):
        upsert(P_DIR / "daily" / f"{y}.parquet", g, ["date", "ticker"])
    if not A.empty:
        upsert(P_DIR / "actions.parquet", A, ["date", "ticker"])

    # 점검
    last = L.groupby("ticker").date.max()
    maxd = last.max()
    stale = last[last < maxd - pd.Timedelta(days=5)]
    bad = int(((L[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    L = L.sort_values(["ticker", "date"])
    ret = L.groupby("ticker").close.pct_change()
    jumps = L[ret.abs() > 0.5]
    if miss:
        R.warning(f"못 받은 종목 {len(miss)}개: {', '.join(miss[:20])}")
    if len(stale):
        R.warning(f"최근 값이 오래된 종목 {len(stale)}개 (상장폐지·티커 변경 가능): {', '.join(stale.index[:15])}")
    if bad:
        R.warning(f"0 이하 가격 행 {bad}개")
    if len(jumps):
        R.warning(f"하루 ±50% 넘는 변동 {len(jumps)}건 (분할 미반영 가능): " + ", ".join(f"{r.ticker} {r.date:%Y-%m-%d}" for r in jumps.head(8).itertuples()))
    R.set(tickers_ok=int(L.ticker.nunique()), missing=len(miss), latest_date=str(maxd.date()),
          first_date=str(L.date.min().date()), rows_new=len(L), dividends=int((A.dividend != 0).sum()) if not A.empty else 0,
          splits=int((A.split != 0).sum()) if not A.empty else 0)
    return R.done()
