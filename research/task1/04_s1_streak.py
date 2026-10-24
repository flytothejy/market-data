"""과제 1-04: S1 연속 상회 검정 (PLAN.md §3·§4).

세부 규칙 (실행 전 고정, 2026-10-24):
- 이력: 종목별 발표를 날짜순으로 놓고, '직전 분기' = 그 종목의 바로 앞 이벤트들
  (칸·경계와 무관하게 과거 이벤트 전부 사용 — 발표 시점에 이미 알려진 정보).
- 신호 S1_k = 직전 k개 발표가 모두 상회. k = 1, 2, 4. 직전 이벤트가 k개 미만이면 제외.
- 목표
  Y1 = 상회(1/0).            기준선 B2 = 직전 8개 발표 상회율(최소 4개).
  Y2 = 서프라이즈 크기 > 같은 달력 분기 전체 발표의 중앙값. 기준선 = 직전 8개 발표의 Y2 비율(최소 4개).
  Y3 = 반응일 초과수익(SPY 대비).  기준선 = 신호 없는 이벤트.
- 효과 D (주 지표):
  Y1, Y2: D = E[Y − 기준선 | S=1] − E[Y − 기준선 | S=0]  (자기 평소 비율을 뺀 뒤의 차이)
  Y3:     D = E[초과수익 | S=1] − E[초과수익 | S=0]
  OLS (Y − 기준선) ~ S, 반응일(없으면 발표일) 기준 날짜별 묶음 표준오차, 단측 p.
  참고 지표로 P(Y1|S=1) vs 같은 해 전체 상회율(B1)도 함께 낸다.
- 판정: 설계 칸 D > 0 이면 확인①·② 를 본다. 두 칸 모두 D > 0 & 단측 p < 0.05 이고,
  Y3는 추가로 S=1 이벤트 매수(발표 전 종가→반응일 종가) 원수익 − 왕복 0.1% > 0 이면
  최종 칸을 한 번 본다.
- 국면(상승/하락)·시기별 D 는 설계 칸에서만 참고로 낸다.
"""
import os, json, datetime
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "task1", "out")
ev = pd.read_csv(os.path.join(ROOT, "data", "events.csv"), parse_dates=["date", "rday"])
ev = ev.sort_values(["t", "date"]).reset_index(drop=True)

# 목표 Y2
ev["cq"] = ev["date"].dt.to_period("Q")
med = ev.groupby("cq")["surp"].transform("median")
ev["y2"] = np.where(ev["surp"].notna(), (ev["surp"] > med).astype(float), np.nan)
ev["y1"] = (ev["cls"] == "beat").astype(float)

g = ev.groupby("t")
prev_beat = g["y1"].shift(1)
ev["n_prev"] = g.cumcount()
for k in (1, 2, 4):
    s = g["y1"].transform(lambda x, k=k: x.shift(1).rolling(k).min())
    ev[f"s1_{k}"] = s
ev["b2_y1"] = g["y1"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).mean())
ev["b2_y2"] = g["y2"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).mean())
ev["b1"] = ev.groupby("year")["y1"].transform("mean")
ev["cdate"] = ev["rday"].fillna(ev["date"]).dt.strftime("%Y-%m-%d")
ev["era"] = pd.cut(ev["year"], [1990, 2009, 2014, 2019, 2030], labels=["~2009", "2010-14", "2015-19", "2020~"])


def test(df, sig, target):
    if target == "Y1":
        d = df.dropna(subset=[sig, "b2_y1"]).copy(); d["y"] = d["y1"] - d["b2_y1"]
    elif target == "Y2":
        d = df.dropna(subset=[sig, "y2", "b2_y2"]).copy(); d["y"] = d["y2"] - d["b2_y2"]
    else:
        d = df.dropna(subset=[sig, "abret"]).copy(); d["y"] = d["abret"]
    d["S"] = d[sig]
    if d["S"].nunique() < 2 or len(d) < 50:
        return None
    m = smf.ols("y ~ S", data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cdate"])[0]})
    D, t = m.params["S"], m.tvalues["S"]
    from scipy.stats import norm
    p = 1 - norm.cdf(t)
    on = d[d["S"] == 1]
    r = {"n": len(d), "n_on": len(on), "share_on": len(on) / len(d), "D": D, "t": t, "p1": p,
         "mean_on": on["y"].mean(), "mean_off": d.loc[d["S"] == 0, "y"].mean()}
    if target == "Y1":
        r["P_beat_on"] = on["y1"].mean(); r["B1_on"] = on["b1"].mean(); r["B2_on"] = on["b2_y1"].mean()
    if target == "Y3":
        r["raw_on_net"] = on["ret"].mean() - 0.001
        r["up_on"] = (on["abret"] > 0).mean(); r["up_off"] = (d.loc[d["S"] == 0, "abret"] > 0).mean()
    return r


rows, logs = [], []
today = datetime.date.today().isoformat()
sigs = ["s1_1", "s1_2", "s1_4"]
for sig in sigs:
    for tg in ["Y1", "Y2", "Y3"]:
        res = {}
        res["설계"] = test(ev[ev["cell"] == "설계"], sig, tg)
        go = res["설계"] is not None and res["설계"]["D"] > 0
        if go:
            for c in ["확인1", "확인2"]:
                res[c] = test(ev[ev["cell"] == c], sig, tg)
            ok = all(res[c] and res[c]["D"] > 0 and res[c]["p1"] < 0.05 for c in ["확인1", "확인2"])
            if tg == "Y3":
                ok = ok and all(res[c]["raw_on_net"] > 0 for c in ["설계", "확인1", "확인2"])
            if ok:
                res["최종"] = test(ev[ev["cell"] == "최종"], sig, tg)
        for c, r in res.items():
            if r is None:
                continue
            rows.append({"signal": sig, "target": tg, "cell": c, **r})
            logs.append([f"T1-S1-{sig}-{tg}-{c}", today, 1, "연속 상회가 평소 비율 이상을 알려주나", "S1",
                         sig.split("_")[1], tg, c, r["n"], "D", round(r["D"], 5),
                         "", "", round(r["p1"], 4), f"n_on={r['n_on']}"])

res = pd.DataFrame(rows)
res.to_csv(os.path.join(OUT, "s1_results.csv"), index=False)
with open(os.path.join(ROOT, "log.csv"), "a") as f:
    for l in logs:
        f.write(",".join(str(x) for x in l) + "\n")

# 설계 칸 국면·시기 참고
ref = []
dz = ev[ev["cell"] == "설계"]
for sig in sigs:
    for tg in ["Y1", "Y2", "Y3"]:
        for col in ["regime", "era"]:
            for v, sub in dz.groupby(col, observed=True):
                r = test(sub, sig, tg)
                if r:
                    ref.append({"signal": sig, "target": tg, "split": col, "value": v, "n": r["n"], "D": r["D"], "p1": r["p1"]})
pd.DataFrame(ref).to_csv(os.path.join(OUT, "s1_design_splits.csv"), index=False)

pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(res.drop(columns=["t"]).to_string(index=False))
print("\n설계 칸 분할 참고"); print(pd.DataFrame(ref).pivot_table(index=["signal", "target"], columns=["split", "value"], values="D").to_string())
