"""과제 1-05b: S3 합격 신호의 누수 점검 (새 가설 아님).
(a) 8-K로 시각 확인된 이벤트만, (b) 창 끝을 하루 앞당김(반응일 2거래일 전 종가까지).
경계값은 05와 같은 방식(설계 칸 분위)."""
import os, numpy as np, pandas as pd
from common import load_events, test, OUT, DATA
ev = load_events(); ev = ev[ev["rday"].notna()].copy()
spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))["Close"]; cal = spy.index; ls = np.log(spy.values)
ev["_pos"] = cal.searchsorted(ev["rday"].values); ev["_i"] = np.arange(len(ev))
c = {k: np.full(len(ev), np.nan) for k in ["20", "5", "20g", "5g"]}
for t, g in ev.groupby("t"):
    lc = np.log(pd.read_parquet(os.path.join(DATA, "prices", f"{t}.parquet"))["Close"].reindex(cal).values)
    for pos, i in zip(g["_pos"].values, g["_i"].values):
        for w in (20, 5):
            for gap, key in ((1, str(w)), (2, f"{w}g")):
                e = pos - gap; s = e - w
                if s < 0 or np.isnan(lc[s:e + 1]).any(): continue
                c[key][i] = (np.exp(lc[e] - lc[s]) - 1) - (np.exp(ls[e] - ls[s]) - 1)
rows = []
for key in c:
    ev["car"] = c[key]; hi = ev.loc[ev.cell == "설계", "car"].quantile(0.8)
    ev["S"] = np.where(ev["car"].notna(), (ev["car"] >= hi).astype(float), np.nan)
    for sub_name, sub in [("전체", ev), ("8k만", ev[ev.timing_src == "8k"])]:
        for tg in ["Y1", "Y2"]:
            for cell in ["설계", "확인1", "확인2", "최종"]:
                r = test(sub[sub.cell == cell], "S", tg)
                rows.append({"window": key, "sample": sub_name, "target": tg, "cell": cell, "n_on": r["n_on"], "D": r["D"], "p1": r["p1"]})
df = pd.DataFrame(rows); df.to_csv(os.path.join(OUT, "s3_robust.csv"), index=False)
print(df.pivot_table(index=["window", "sample", "target"], columns="cell", values="D").round(4).to_string())
