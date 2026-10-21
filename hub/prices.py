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


def expected_day(now=None):
    """지금 기준 마지막으로 끝난 미국 거래일 (휴장일은 무시 — 휴장일이면 그날 시간봉이 없어 아무것도 안 채워짐)"""
    ny = (now or pd.Timestamp.now(tz="America/New_York")).tz_convert("America/New_York")
    d = ny.normalize().tz_localize(None)
    if ny.hour * 60 + ny.minute < 16 * 60 + 10:
        d -= pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def intraday_fill(tickers, upto):
    """일봉 마지막 날 종가가 비어 오는 경우(야후 장애, 2026-10-21 실제 발생: 전 종목 NaN) 시간봉으로 그날 일봉을 만듦.
    잠정값 — 다음 실행이 최근 1개월 일봉을 다시 받으며 야후 값으로 덮어씀."""
    out = []
    for i in range(0, len(tickers), CHUNK):
        part = tickers[i:i + CHUNK]
        try:
            raw = yf.download(part, interval="1h", period="5d", auto_adjust=False, group_by="ticker", threads=True, progress=False)
        except Exception as e:
            log(f"  시간봉 실패: {str(e)[:80]}")
            continue
        if raw is None or raw.empty:
            continue
        single = not isinstance(raw.columns, pd.MultiIndex)
        for t in part:
            try:
                d = raw if single else raw[t]
            except KeyError:
                continue
            d = d.dropna(subset=["Close"])
            if d.empty:
                continue
            idx = d.index.tz_convert("America/New_York") if d.index.tz is not None else d.index
            day = idx.normalize().tz_localize(None) if idx.tz is not None else idx.normalize()
            for dt_, g in d.groupby(day):
                if dt_ > upto or len(g) < 3:
                    continue
                out.append({"date": dt_, "ticker": t, "open": g["Open"].iloc[0], "high": g["High"].max(), "low": g["Low"].min(),
                            "close": g["Close"].iloc[-1], "adj_close": g["Close"].iloc[-1], "volume": int(g["Volume"].fillna(0).sum())})
    F = pd.DataFrame(out)
    if not F.empty:
        for c in ("open", "high", "low", "close", "adj_close"):
            F[c] = F[c].astype("float32")
    return F


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
    # 최근 거래일이 빠진 종목 다시 받기 — 일괄 다운로드가 마지막 날을 일부 종목에만 주는 경우가 있음 (2026-10-20 실제 발생: 2/1194)
    cov = 1.0
    if not L.empty and old_t:
        last = L.date.max()
        have_last = set(L[L.date == last].ticker)
        lagging = [t for t in old_t if t not in have_last]
        for rnd in range(2):
            if not lagging or len(lagging) < 0.02 * len(old_t):
                break
            log(f"  최근 거래일({last:%Y-%m-%d}) 빠진 {len(lagging)}종목 다시 받기 ({rnd + 1}차)")
            time.sleep(20 * (rnd + 1))
            for i in range(0, len(lagging), CHUNK):
                part = lagging[i:i + CHUNK]
                try:
                    raw = yf.download(part, auto_adjust=False, actions=True, group_by="ticker", threads=False, progress=False, period="5d")
                    L2, A2 = to_long(raw, part)
                    if not L2.empty:
                        L = pd.concat([L, L2], ignore_index=True)
                        if not A2.empty:
                            A = pd.concat([A, A2], ignore_index=True)
                except Exception as e:
                    log(f"  재시도 실패: {str(e)[:80]}")
            have_last = set(L[L.date == last].ticker)
            lagging = [t for t in old_t if t not in have_last]
        # 일봉 마지막 날 종가가 통째로 비어 오는 경우 → 시간봉으로 채움 (전 종목이 빠지면 last 자체가 하루 이르게 잡힘)
        exp = expected_day()
        if last < exp:                                      # 휴장일이면 SPY 시간봉에도 그날이 없음 → 건너뜀
            pr = intraday_fill(["SPY"], exp)
            if pr.empty or pr.date.max() < exp:
                exp = last
        if lagging and len(lagging) > 300 or last < exp:
            need = lagging if last >= exp else old_t
            log(f"  일봉 마지막 날이 비어 시간봉으로 채우기: {len(need)}종목 (기대 거래일 {exp:%Y-%m-%d})")
            F = intraday_fill(need, exp)
            if not F.empty:
                have = set(zip(L.ticker, L.date))
                F = F[[(t, d) not in have for t, d in zip(F.ticker, F.date)]]
                L = pd.concat([L, F], ignore_index=True)
                R.set(intraday_filled=len(F))
                R.warning(f"야후 일봉에 {F.date.max():%Y-%m-%d} 종가가 없어 시간봉으로 잠정 채움 {len(F)}행 (다음 실행에서 일봉으로 교체)")
            last = L.date.max()
            have_last = set(L[L.date == last].ticker)
            lagging = [t for t in old_t if t not in have_last]
        if lagging and len(lagging) <= 300:                 # 그래도 빠지면 종목별로 (느리지만 확실)
            for t in lagging:
                try:
                    h = yf.Ticker(t).history(period="5d", auto_adjust=False, actions=True)
                    if not h.empty:
                        L2, A2 = to_long(h, [t])
                        if not L2.empty:
                            L = pd.concat([L, L2], ignore_index=True)
                            if not A2.empty:
                                A = pd.concat([A, A2], ignore_index=True)
                except Exception:
                    pass
            have_last = set(L[L.date == last].ticker)
            lagging = [t for t in old_t if t not in have_last]
        if not A.empty:
            A = A.drop_duplicates(["date", "ticker"], keep="last")
        L = L.drop_duplicates(["date", "ticker"], keep="last")
        cov = 1 - len(lagging) / len(old_t)
        R.set(latest_day_coverage=f"{cov*100:.1f}%")
        if lagging:
            R.warning(f"{'치명: ' if cov < 0.9 else ''}최근 거래일({last:%Y-%m-%d}) 가격이 없는 종목 {len(lagging)}개: {', '.join(lagging[:15])}")
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
    ratio = L.close / L.groupby("ticker").close.shift(1)
    # 분할 의심: 하루 변화가 흔한 분할 비율(2·3·4·5·10배 또는 그 역수)에 가깝고 분할 기록이 없는 경우
    near = lambda x: any(abs(x / k - 1) < 0.06 for k in (2, 3, 4, 5, 10, 1/2, 1/3, 1/4, 1/5, 1/10))
    cand = L[(ratio > 1.8) | (ratio < 0.55)].assign(r=ratio)
    cand = cand[cand.r.apply(near)]
    if not A.empty and not cand.empty:
        sp = A[A.split != 0][["ticker", "date"]]
        cand = cand.merge(sp.assign(has=1), on=["ticker", "date"], how="left")
        cand = cand[cand.has.isna()]
    jumps = cand
    if miss:
        R.warning(f"못 받은 종목 {len(miss)}개: {', '.join(miss[:20])}")
    if len(stale):
        R.warning(f"최근 값이 오래된 종목 {len(stale)}개 (상장폐지·티커 변경 가능): {', '.join(stale.index[:15])}")
    if bad:
        R.warning(f"0 이하 가격 행 {bad}개")
    if len(jumps):
        R.warning(f"분할 미반영 의심 {len(jumps)}건: " + ", ".join(f"{r.ticker} {r.date:%Y-%m-%d}" for r in jumps.head(8).itertuples()))
    R.set(tickers_ok=int(L.ticker.nunique()), missing=len(miss), latest_date=str(maxd.date()),
          first_date=str(L.date.min().date()), rows_new=len(L), dividends=int((A.dividend != 0).sum()) if not A.empty else 0,
          splits=int((A.split != 0).sum()) if not A.empty else 0)
    return R.done(ok=cov >= 0.9)
