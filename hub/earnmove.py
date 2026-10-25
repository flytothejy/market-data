"""실적 발표 반응 이력과 예상 변동폭 (연구 과제 2-1, 계수는 spec 값 그대로)

반응 이력 (N5, data/hub/derived/earn_moves.parquet)
- 8-K 항목 2.02의 접수 시각(뉴욕)으로 반응일을 정함 (JSON 시각 보정은 moves() 주석): 장 시작(9:30) 전이면 그날, 아니면 다음 거래일
- 반응 = 그날 종목 수익률 − SPY 수익률 (수정종가). 같은 회사 45일 안 중복은 첫 건만
화면 값
- 지난 8번 평균 = 반응일 |초과수익| 평균 (4번 이상일 때)
- 이번 시즌 같은 업종 = 같은 SIC 2자리, 기준일 전 90일 안 다른 종목 반응 |초과수익| 평균 (5건 미만이면 전체 평균)
- 모델 예상치는 화면에 쓰지 않고 실시간 기록(research_live/earn_move)에만 남김
"""
import json, math
from pathlib import Path

import numpy as np
import pandas as pd

SPEC_P = Path(__file__).resolve().parent / "spec" / "tickermap_spec.json"


def moves(FL, pxg, sic=None):
    """FL: filings(cik·ticker·form·items·accepted), pxg: {티커: 가격 프레임} → 반응 이력 DataFrame"""
    spy = pxg.get("SPY")
    if spy is None or FL is None or not len(FL):
        return pd.DataFrame()
    days = pd.DatetimeIndex(spy.date)
    sret = spy.set_index("date").adj_close.pct_change()
    e = FL[(FL.form == "8-K") & FL["items"].astype(str).str.contains("2.02", regex=False) & FL.accepted.notna()].copy()
    # 주의: 제출 목록 JSON의 접수 시각은 'Z'가 붙어 있지만 실제 UTC보다 뉴욕 시차만큼 더 밀려 있음
    #   (JPM 2026-10-13 JSON 14:30:38Z ↔ 공시 머리말 ACCEPTANCE-DATETIME 06:30:38 뉴욕, NVDA 00:21Z ↔ 16:21)
    #   → 뉴욕 시각으로 바꾼 뒤 시차(−4~5시간)를 한 번 더 적용
    ny = pd.to_datetime(e.accepted, utc=True, errors="coerce").dt.tz_convert("America/New_York")
    e["ts"] = ny + pd.to_timedelta([x.utcoffset() if pd.notna(x) else pd.Timedelta(0) for x in ny]).values
    e["ts"] = e["ts"].where(ny.notna())
    e = e.dropna(subset=["ts"]).sort_values("ts")
    rep = FL[FL.form.isin(["10-Q", "10-K", "20-F", "40-F"])].groupby("ticker").filed.apply(lambda x: sorted(set(pd.to_datetime(x).dt.normalize())))
    out = []
    for t, g in e.groupby("ticker"):
        # 2.02는 인도량 발표 등에도 쓰임(테슬라) → 분기·연간 보고서 제출 전 40일 안의 마지막 2.02만 실적 발표로 봄 (연구 규칙에 더한 것, build.py er_hist와 같은 규칙)
        rq = rep.get(t, [])
        if len(rq):
            d8 = g.ts.dt.tz_localize(None).dt.normalize()
            keep = set()
            for f in rq:
                c = g[(d8 >= f - pd.Timedelta(days=40)) & (d8 <= f + pd.Timedelta(days=1))]
                if len(c):
                    keep.add(c.index[-1])
            if len(g) and g.index[-1] not in keep and d8.iloc[-1] > rq[-1]:
                keep.add(g.index[-1])                    # 방금 발표하고 보고서는 아직 안 낸 경우
            g = g.loc[sorted(keep, key=lambda i: g.ts[i])] if keep else g.iloc[:0]
        px = pxg.get(t)
        if px is None or len(px) < 30:
            continue
        r = px.set_index("date").adj_close.pct_change()
        last = None
        for x in g.itertuples():
            if last is not None and (x.ts - last).days < 45:
                continue
            last = x.ts
            d0 = pd.Timestamp(x.ts.date())
            pre = x.ts.hour * 60 + x.ts.minute < 9 * 60 + 30
            i = days.searchsorted(d0) if pre else days.searchsorted(d0 + pd.Timedelta(days=1))
            if i >= len(days):
                continue
            rd = days[i]
            if rd not in r.index or pd.isna(r.get(rd)) or pd.isna(sret.get(rd)):
                continue
            out.append({"ticker": t, "cik": int(x.cik), "accepted": str(x.ts), "react": rd, "pre": bool(pre),
                        "ex": float(r[rd] - sret[rd]), "sic2": (sic or {}).get(int(x.cik), "")})
    return pd.DataFrame(out)


def simple(M, t, n=8):
    """지난 n번 평균 |초과수익| (4번 이상) → (평균, 횟수)"""
    m = M[M.ticker == t].sort_values("react").tail(n) if len(M) else M
    if len(m) < 4:
        return None, len(m)
    return float(m.ex.abs().mean()), len(m)


def season(M, sic2, t, ref):
    """같은 SIC 2자리, ref 전 90일 안 다른 종목 평균 |반응| (5건 미만이면 전체 평균)"""
    if not len(M):
        return None, "none"
    w = M[(M.react <= ref) & (M.react > ref - pd.Timedelta(days=90)) & (M.ticker != t)]
    s = w[w.sic2 == sic2] if sic2 else w.iloc[:0]
    if len(s) >= 5:
        return float(s.ex.abs().mean()), "sic"
    return (float(w.ex.abs().mean()), "all") if len(w) else (None, "none")


def model(f1, g, spy, f3, after):
    """연구 회귀 예상치 |변동| (화면 표시 없음). g/spy: 가격 프레임"""
    c = json.loads(SPEC_P.read_text(encoding="utf-8"))["earnings_move"]["coef"]
    try:
        a = g.set_index("date").adj_close.pct_change()
        b = spy.set_index("date").adj_close.pct_change()
        ex = (a - b).dropna()
        f2 = math.log(float(ex.tail(60).std()))
        r20 = float(g.adj_close.iloc[-1] / g.adj_close.iloc[-21] - 1) - float(spy.adj_close.iloc[-1] / spy.adj_close.iloc[-21] - 1)
        f4 = math.log(1 + abs(r20))
        tail = g.tail(252)
        f5 = math.log(float((tail.close * tail.volume).mean()))
        x = {"f1": math.log(f1), "f2": f2, "f3": math.log(f3), "f4": f4, "f5": f5, "f6": 1.0 if after else 0.0}
        lg = c["const"] + sum(c[k] * v for k, v in x.items())
        return math.exp(lg), x
    except Exception:
        return None, {}
