"""옵션 요약 — 내재변동성(ATM, 약 30일), 풋/콜 비율, 왜곡(skew) — yfinance 옵션 체인

대상: 시가총액 상위 200종목 + ETF 전체
저장: data/hub/options/YYYY.parquet
  date, ticker, spot, exp30, dte30, iv_atm30, iv_put90, iv_call110, skew, exp_near, iv_atm_near,
  pc_vol, pc_oi, call_vol, put_vol, call_oi, put_oi   (거래량·미결제약정은 가까운 2개 만기 합)
※ 장 마감 후의 값이지만 yfinance 옵션 값은 지연·누락이 있을 수 있음 → 점검표의 누락 수 확인
"""
import time, datetime as dt
import numpy as np, pandas as pd
import yfinance as yf

from .core import DATA, Run, log, read, upsert
from . import universe

O_DIR = DATA / "options"
N_STOCKS = 200


def atm_iv(ch, spot):
    ivs = []
    for side in (ch.calls, ch.puts):
        d = side[(side.impliedVolatility > 0.01) & (side.impliedVolatility < 5)]
        if d.empty:
            continue
        d = d.iloc[(d.strike - spot).abs().argsort()[:2]]
        ivs += list(d.impliedVolatility)
    return float(np.mean(ivs)) if ivs else np.nan


def iv_at(side, k):
    d = side[(side.impliedVolatility > 0.01) & (side.impliedVolatility < 5)]
    if d.empty:
        return np.nan
    return float(d.iloc[(d.strike - k).abs().argsort()[:1]].impliedVolatility.iloc[0])


def one(t, spot, today):
    T = yf.Ticker(t)
    exps = list(T.options or [])
    if not exps:
        return None
    ds = [(e, (dt.date.fromisoformat(e) - today).days) for e in exps]
    ds = [x for x in ds if x[1] >= 1]
    if not ds:
        return None
    near = ds[0]
    e30 = min(ds, key=lambda x: abs(x[1] - 30))
    c30 = T.option_chain(e30[0])
    if spot is None or np.isnan(spot):
        spot = float(pd.concat([c30.calls.strike]).median())
    rec = {"ticker": t, "spot": spot, "exp30": e30[0], "dte30": e30[1], "iv_atm30": atm_iv(c30, spot),
           "iv_put90": iv_at(c30.puts, spot * 0.9), "iv_call110": iv_at(c30.calls, spot * 1.1),
           "exp_near": near[0]}
    chains = [c30]
    if near[0] != e30[0]:
        cn = T.option_chain(near[0])
        rec["iv_atm_near"] = atm_iv(cn, spot)
        chains.append(cn)
    else:
        rec["iv_atm_near"] = rec["iv_atm30"]
    cv = sum(float(c.calls.volume.fillna(0).sum()) for c in chains)
    pv = sum(float(c.puts.volume.fillna(0).sum()) for c in chains)
    co = sum(float(c.calls.openInterest.fillna(0).sum()) for c in chains)
    po = sum(float(c.puts.openInterest.fillna(0).sum()) for c in chains)
    rec.update(call_vol=cv, put_vol=pv, call_oi=co, put_oi=po,
               pc_vol=pv / cv if cv else np.nan, pc_oi=po / co if co else np.nan,
               skew=rec["iv_put90"] - rec["iv_call110"])
    return rec


def run(limit=0, **_):
    R = Run("options")
    U = universe.load()
    P = read(DATA / "profile" / "profile.parquet")
    cap = dict(zip(P.ticker, pd.to_numeric(P.get("marketCap"), errors="coerce"))) if not P.empty else {}
    st = U[U.kind == "stock"].assign(cap=lambda d: d.ticker.map(cap)).sort_values("cap", ascending=False)
    tickers = list(st.ticker[:N_STOCKS]) + list(U[U.kind == "etf"].ticker)
    if limit:
        tickers = tickers[:limit]
    # 현재가는 우리 가격 파일의 최근 종가
    pf = sorted((DATA / "prices" / "daily").glob("*.parquet"))
    spot = {}
    if pf:
        px = pd.read_parquet(pf[-1], columns=["date", "ticker", "close"])
        spot = px.sort_values("date").groupby("ticker").close.last().to_dict()
        asof = px.date.max().date()
    else:
        asof = dt.date.today()
    today = dt.date.today()
    rows, none, fail = [], [], []
    for i, t in enumerate(tickers):
        try:
            r = one(t, spot.get(t), today)
            if r is None:
                none.append(t)
            else:
                rows.append(r)
        except Exception as e:
            fail.append(f"{t}: {str(e)[:40]}")
        time.sleep(0.2)
        if (i + 1) % 50 == 0:
            log(f"  옵션 {i+1}/{len(tickers)}")
    if not rows:
        R.warning("치명: 받은 옵션 정보가 없음")
        return R.done(ok=False)
    D = pd.DataFrame(rows).assign(date=pd.Timestamp(asof))
    upsert(O_DIR / f"{asof.year}.parquet", D, ["date", "ticker"])
    if none:
        R.warning(f"옵션이 없는 종목 {len(none)}개: {', '.join(none[:15])}")
    if fail:
        R.warning(f"실패 {len(fail)}개 — 예: {fail[0]}")
    ok_iv = D.iv_atm30.notna().mean()
    R.set(requested=len(tickers), ok=len(rows), no_options=len(none), failed=len(fail), asof=str(asof),
          iv_coverage=f"{ok_iv*100:.0f}%", median_iv30=f"{D.iv_atm30.median()*100:.0f}%",
          spy_iv30=f"{D.set_index('ticker').iv_atm30.get('SPY', np.nan)*100:.1f}%", rows_new=len(D))
    return R.done()
