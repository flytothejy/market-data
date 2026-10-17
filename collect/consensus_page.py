#!/usr/bin/env python3
"""
컨센서스 페이지 데이터 생성: consensus/*/*.csv.gz → docs/consensus_data.json (페이지 docs/consensus.html 이 읽음)
  - 최신일 종목별 전망·목표가·의견·서프라이즈
  - 순상향(내년 EPS, 최근 30일 상향−하향), 순상향률(÷애널리스트 수), 전일·7일 전 대비 변화
  - 일별 시장 전체 상향 우세 비율 이력
사용: python collect/consensus_page.py
"""
import csv, glob, json, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_N = 10                              # 순위표·비율 집계는 내년 EPS 애널리스트 10명 이상만


def day_metrics(d):
    """하루치 파일 → 종목별 순상향·순상향률·내년 EPS 90일 변화"""
    g = lambda b, p: d[(d.block == b) & (d.period == p)].pivot_table(index="ticker", columns="field", values="value")
    r, t, n = g("eps_rev", "+1y"), g("eps_trend", "+1y"), g("eps", "+1y")
    x = pd.DataFrame(index=sorted(d.ticker.unique()))
    x["up"] = r.get("upLast30days"); x["dn"] = r.get("downLast30days")
    x["n"] = n.get("numberOfAnalysts")
    x["net"] = x.up - x.dn
    x["ratio"] = x.net / np.maximum(x.n, x.up + x.dn)     # 수정 건수가 현재 애널리스트 수보다 많을 수 있어 분모 보정 (−1~+1)
    x["chg90"] = t.get("current") / t.get("90daysAgo") - 1 if "90daysAgo" in t else np.nan
    return x


def num(v, k=4):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), k)


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "consensus", "*", "*.csv.gz")))
    if not files:
        print("컨센서스 파일 없음"); return
    names = {r["ticker"]: r["name"] for r in csv.DictReader(open(os.path.join(ROOT, "sp500_names.csv"), encoding="utf-8"))}
    days = {os.path.basename(f)[:10]: f for f in files}
    dates = sorted(days)
    last = dates[-1]
    D = pd.read_csv(days[last])
    M = {dt: day_metrics(pd.read_csv(days[dt]) if dt != last else D) for dt in dates[-8:]}
    cur = M[last]
    prev = M[dates[-2]] if len(dates) >= 2 else None
    wk = M[dates[-6]] if len(dates) >= 6 else None          # 영업일 5일 전 ≈ 1주
    # 시장 전체 이력 (모든 날짜)
    hist = []
    for dt in dates:
        m = M[dt] if dt in M else day_metrics(pd.read_csv(days[dt]))
        m = m[m.n >= MIN_N]
        hist.append(dict(d=dt, up=int((m.net > 0).sum()), dn=int((m.net < 0).sum()), n=int(len(m))))
    T = {}
    for tk, g in D.groupby("ticker"):
        piv = lambda b: g[g.block == b].pivot_table(index="period", columns="field", values="value")
        o = dict(name=names.get(tk, ""))
        for b, key in (("rev", "rev"), ("eps", "eps")):
            p = piv(b)
            o[key] = {per: dict(avg=num(r.get("avg")), lo=num(r.get("low")), hi=num(r.get("high")), n=num(r.get("numberOfAnalysts"), 0),
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
    out = dict(date=last, prev=dates[-2] if len(dates) >= 2 else None, wk=dates[-6] if len(dates) >= 6 else None,
               min_n=MIN_N, n_tickers=len(T), hist=hist, t=T)
    fp = os.path.join(ROOT, "docs", "consensus_data.json")
    json.dump(out, open(fp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"컨센서스 페이지 데이터: {last}, {len(T)}종목, 이력 {len(hist)}일 → {fp} ({os.path.getsize(fp)//1024}KB)")


if __name__ == "__main__":
    main()
