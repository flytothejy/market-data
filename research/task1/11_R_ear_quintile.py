"""과제 1-11 (기술 통계, 새 검정 아님): 반응 5분위별 60일 표류 — 지금 종목만 vs 상장폐지 포함."""
import os, numpy as np, pandas as pd
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "10_tests_R.py")).read().split('E["cdate"]')[0]
g = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "10_tests_R.py")}; exec(src, g); E = g["E"]
print("inf:", int(np.isinf(E[["y4_20", "y4_60", "car20", "car5"]]).values.sum()))
x = E[~E["cross_60"].astype(bool)].dropna(subset=["y4_60"]).copy()
x["q"] = pd.qcut(x["abret"].rank(method="first"), 5, labels=["최하", "2", "3", "4", "최상"])
t = pd.concat({"지금 종목만": x[x.src == "cur"].groupby("q", observed=True)["y4_60"].mean(),
               "상장폐지 포함": x.groupby("q", observed=True)["y4_60"].mean(),
               "상장폐지 비율": x.groupby("q", observed=True)["src"].apply(lambda s: (s == "delisted").mean())}, axis=1)
t.to_csv(os.path.join(g["OUT"], "R_ear_quintile_60.csv")); print(t.round(4).to_string())
