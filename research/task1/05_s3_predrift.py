"""과제 1-05: S3 발표 전 주가 흐름 검정 (PLAN.md §3·§4).

세부 규칙 (실행 전 고정, 2026-10-24):
- 창: 반응일 직전 거래일 종가까지 (장후 발표는 발표일 종가, 장전 발표는 전날 종가 — 발표 전 정보만).
  CAR_w = 종목 누적수익(w 거래일) − SPY 누적수익(같은 w 거래일). w = 20, 5.
  창 안에 종목 가격이 하나라도 비면 제외.
- 분위 경계: 설계 칸 이벤트의 CAR_w 20%·80% 분위수를 구해, 모든 칸에 같은 경계를 적용.
- 신호 4개: s3_20_top (CAR_20 ≥ 설계 80% 분위), s3_20_bot (CAR_20 ≤ 설계 20% 분위),
           s3_5_top, s3_5_bot. 각각 S=1 vs 나머지(S=0).
  top의 D>0 은 "발표 전 강세가 이어진다", bot의 D>0 은 "발표 전 약세가 되돌려진다".
  두 방향을 각각 단측 D>0 으로 본다.
- 목표·기준선·판정: 04_s1_streak.py와 동일 (common.py).
- 검정 수: 신호 4 × 목표 3 = 12.
"""
import os, json
import numpy as np, pandas as pd
from common import load_events, run, design_splits, OUT, DATA

ev = load_events()
ev = ev[ev["rday"].notna()].copy()

spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))["Close"]
cal = spy.index
lspy = np.log(spy.values)
car = {20: np.full(len(ev), np.nan), 5: np.full(len(ev), np.nan)}
pos_r = cal.searchsorted(ev["rday"].values)
ev["_pos"] = pos_r
ev["_i"] = np.arange(len(ev))
for t, g in ev.groupby("t"):
    p = os.path.join(DATA, "prices", f"{t}.parquet")
    if not os.path.exists(p):
        continue
    lc = np.log(pd.read_parquet(p)["Close"].reindex(cal).values)
    for pos, i in zip(g["_pos"].values, g["_i"].values):
        e = pos - 1                                  # 반응일 직전 거래일
        for w in (20, 5):
            s = e - w
            if s < 0:
                continue
            seg = lc[s:e + 1]
            if np.isnan(seg).any():
                continue
            car[w][i] = (np.exp(lc[e] - lc[s]) - 1) - (np.exp(lspy[e] - lspy[s]) - 1)
ev["car20"], ev["car5"] = car[20], car[5]

cut = {}
dz = ev[ev["cell"] == "설계"]
for w in (20, 5):
    lo, hi = dz[f"car{w}"].quantile([0.2, 0.8])
    cut[w] = (lo, hi)
    x = ev[f"car{w}"]
    ev[f"s3_{w}_top"] = np.where(x.notna(), (x >= hi).astype(float), np.nan)
    ev[f"s3_{w}_bot"] = np.where(x.notna(), (x <= lo).astype(float), np.nan)
json.dump({str(k): v for k, v in cut.items()}, open(os.path.join(OUT, "s3_cutoffs.json"), "w"), indent=1)

sigs = ["s3_20_top", "s3_20_bot", "s3_5_top", "s3_5_bot"]
res = run(ev, sigs, "S3", "발표 전 주가 흐름이 서프라이즈·반응을 알려주나", "S3")
res.to_csv(os.path.join(OUT, "s3_results.csv"), index=False)
sp = design_splits(ev, sigs)
sp.to_csv(os.path.join(OUT, "s3_design_splits.csv"), index=False)

pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print("cutoffs (20%, 80%):", {k: tuple(round(v, 4) for v in c) for k, c in cut.items()})
print(res.drop(columns=["t"]).to_string(index=False))
print("\n설계 칸 분할 참고 (D)")
print(sp.pivot_table(index=["signal", "target"], columns=["split", "value"], values="D").to_string())
