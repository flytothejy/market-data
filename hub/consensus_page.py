"""예전 S&P 500 컨센서스 페이지(docs/consensus.html)용 데이터 — 허브가 매일 쌓는 전체 종목 컨센서스에서 만듦
(예전에는 collect/consensus.py가 S&P 500만 따로 야후에서 받아 저장소에 커밋했음 → 중복 수집 정리)
출력 형식은 collect/consensus_page.py와 같음: date, prev, wk, min_n, n_tickers, hist, t
"""
import numpy as np
import pandas as pd

MIN_N = 10                              # 순위표·비율 집계는 내년 EPS 애널리스트 10명 이상만


def day_metrics(d):
    g = lambda b, p: d[(d.block == b) & (d.period == p)].pivot_table(index="ticker", columns="field", values="value")
    r, t, n = g("eps_rev", "+1y"), g("eps_trend", "+1y"), g("eps", "+1y")
    x = pd.DataFrame(index=sorted(d.ticker.unique()))
    x["up"] = r.get("upLast30days"); x["dn"] = r.get("downLast30days")
    x["n"] = n.get("numberOfAnalysts")
    x["net"] = x.up - x.dn
    x["ratio"] = x.net / np.maximum(x.n, x.up + x.dn)
    x["chg90"] = t.get("current") / t.get("90daysAgo") - 1 if "90daysAgo" in t else np.nan
    return x


def num(v, k=4):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, k) if np.isfinite(v) else None


def build(H, names, tickers):
    """H: 허브 컨센서스 이력(long), names: 티커→이름, tickers: 페이지에 담을 종목(S&P 500)"""
    H = H[H.ticker.isin(tickers)]
    if H.empty:
        return None
    by = {d: g for d, g in H.groupby("date")}
    dates = sorted(by)
    last = dates[-1]
    D = by[last]
    M = {d: day_metrics(by[d]) for d in dates}
    cur = M[last]
    prev = M[dates[-2]] if len(dates) >= 2 else None
    wk = M[dates[-6]] if len(dates) >= 6 else None
    hist = []
    for d in dates:
        m = M[d][M[d].n >= MIN_N]
        hist.append(dict(d=d, up=int((m.net > 0).sum()), dn=int((m.net < 0).sum()), n=int(len(m))))
    T = {}
    for tk, g in D.groupby("ticker"):
        piv = lambda b: g[g.block == b].pivot_table(index="period", columns="field", values="value")
        o = dict(name=names.get(tk, ""))
        for b in ("rev", "eps"):
            p = piv(b)
            o[b] = {per: dict(avg=num(r.get("avg")), lo=num(r.get("low")), hi=num(r.get("high")), n=num(r.get("numberOfAnalysts"), 0),
                              g=num(r.get("growth"))) for per, r in p.iterrows()} if len(p) else {}
        p = piv("eps_trend")
        if "+1y" in p.index:
            r = p.loc["+1y"]; o["trend"] = [num(r.get(k)) for k in ("90daysAgo", "60daysAgo", "30daysAgo", "7daysAgo", "current")]
        p = piv("eps_rev")
        if "+1y" in p.index:
            r = p.loc["+1y"]; o["rev30"] = [num(r.get("upLast30days"), 0), num(r.get("downLast30days"), 0)]
            o["rev7"] = [num(r.get("upLast7days"), 0), num(r.get("downLast7Days"), 0)]
        p = piv("pt")
        if "now" in p.index:
            r = p.loc["now"]; o["pt"] = dict(cur=num(r.get("current"), 2), lo=num(r.get("low"), 2), mean=num(r.get("mean"), 2), hi=num(r.get("high"), 2))
        p = piv("rec")
        if "0m" in p.index:
            r = p.loc["0m"]; o["rec"] = [num(r.get(k), 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")]
        p = piv("ehist")
        o["surp"] = [dict(q=str(q), a=num(r.get("epsActual")), e=num(r.get("epsEstimate")), s=num(r.get("surprisePercent"))) for q, r in p.sort_index().iterrows()]
        if tk in cur.index:
            c = cur.loc[tk]
            o.update(net=num(c.net, 0), ratio=num(c.ratio), n1y=num(c.n, 0), chg90=num(c.chg90))
            for lab, ref in (("d1", prev), ("d7", wk)):
                if ref is not None and tk in ref.index and np.isfinite(ref.loc[tk].net) and np.isfinite(c.net):
                    o[lab + "_net"] = num(c.net - ref.loc[tk].net, 0)
                    o[lab + "_ratio"] = num(c.ratio - ref.loc[tk].ratio)
        T[tk] = o
    return dict(date=last, prev=dates[-2] if len(dates) >= 2 else None, wk=dates[-6] if len(dates) >= 6 else None,
                min_n=MIN_N, n_tickers=len(T), hist=hist, t=T)
