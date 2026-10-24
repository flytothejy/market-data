"""과제 1-06b: S2(동종 업체 전부 상회)와 S3(20일 강세)의 중복 점검 — 탐색용, 새 합격 판정 아님.
(Y − 기준선) ~ s2_beat_m2 + s3_20_top, 칸별, 날짜 묶음 표준오차."""
import os, numpy as np, pandas as pd, statsmodels.formula.api as smf
from common import load_events, OUT, DATA
ev = load_events(); ev = ev[ev.rday.notna()].copy()
f2 = pd.read_csv(os.path.join(DATA, "s2_features.csv"), parse_dates=["date"])[["t", "date", "s2_beat_m2"]]
ev = ev.merge(f2, on=["t", "date"], how="left")
spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
ev["_pos"] = cal.searchsorted(ev.rday.values); car = np.full(len(ev), np.nan)
for t, g in ev.groupby("t"):
    lc = np.log(pd.read_parquet(os.path.join(DATA, "prices", f"{t}.parquet"))["Close"].reindex(cal).values)
    for pos, i in zip(g._pos.values, g.index.values):
        e = pos - 1; s = e - 20
        if s >= 0 and not np.isnan(lc[s:e + 1]).any():
            car[i] = (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
ev["car20"] = car; hi = ev.loc[ev.cell == "설계", "car20"].quantile(.8)
ev["s3"] = np.where(ev.car20.notna(), (ev.car20 >= hi).astype(float), np.nan)
ev["s2"] = ev["s2_beat_m2"]
rows = []
for tg, ycol, b in [("Y1", "y1", "b2_y1"), ("Y2", "y2", "b2_y2")]:
    for cell in ["설계", "확인1", "확인2", "최종"]:
        d = ev[ev.cell == cell].dropna(subset=["s2", "s3", ycol, b]).copy(); d["y"] = d[ycol] - d[b]
        m = smf.ols("y ~ s2 + s3", d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.cdate)[0]})
        rows.append({"target": tg, "cell": cell, "n": len(d), "corr_s2_s3": d[["s2", "s3"]].corr().iloc[0, 1],
                     "D_s2": m.params.s2, "p_s2": m.pvalues.s2 / 2, "D_s3": m.params.s3, "p_s3": m.pvalues.s3 / 2})
df = pd.DataFrame(rows); df.to_csv(os.path.join(OUT, "s2_vs_s3.csv"), index=False)
pd.set_option("display.float_format", "{:.4f}".format); print(df.to_string(index=False))
