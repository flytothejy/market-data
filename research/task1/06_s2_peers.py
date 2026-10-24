"""과제 1-06: S2 먼저 발표한 동종 업체 검정 (PLAN.md §3·§4).

세부 규칙 (실행 전 고정, 2026-10-24):
- 동종 업체: 티커맵 universe의 같은 세부 산업(`ind`, 현재 분류 — 과거 분류 변경은 반영 못 함).
- 대상 이벤트 i 의 정보 시점 = 반응일 직전. 동종 업체 이벤트 j 는
  반응일_j < 반응일_i 이고 반응일_j ≥ 반응일_i − 30일(달력), 종목 ≠ i 인 것.
  (반응일이 없는 이벤트는 대상·동종 모두에서 제외.)
- 지표 2개: peer_beat = 동종 업체 상회 비율, peer_ab = 동종 업체 반응일 초과수익 평균.
- 최소 동종 업체 수 m = 2, 3. 미달이면 신호 없음(제외).
- 신호 = 지표가 설계 칸 분포의 80% 분위수 이상이면 1 (S3와 같은 방식). 경계는 설계 칸에서만 계산해 모든 칸에 적용.
  → s2_beat_m2, s2_beat_m3, s2_ab_m2, s2_ab_m3. 가설 방향: 동종 업체가 좋았으면 나도 좋다 (D>0).
- 목표·기준선·판정: common.py (S1·S3와 동일). 검정 수: 4 × 3 = 12.
"""
import os, json
import numpy as np, pandas as pd
from common import load_events, run, design_splits, OUT, DATA

ev = load_events()
uni = pd.read_csv(os.path.join(DATA, "universe.csv"))[["t", "ind"]]
ev = ev[ev["rday"].notna()].merge(uni, on="t", how="left").reset_index(drop=True)

for c in ["pb", "pa", "pn"]:
    ev[c] = np.nan
win = np.timedelta64(30, "D")
for ind, g in ev.groupby("ind"):
    g = g.sort_values("rday")
    rd = g["rday"].values; tk = g["t"].values; y1 = g["y1"].values; ab = g["abret"].values
    for k, i in enumerate(g.index):
        lo = np.searchsorted(rd, rd[k] - win, side="left")
        hi = np.searchsorted(rd, rd[k], side="left")          # 반응일_j < 반응일_i
        if hi <= lo:
            ev.at[i, "pn"] = 0; continue
        m = tk[lo:hi] != tk[k]
        n = int(m.sum()); ev.at[i, "pn"] = n
        if n:
            ev.at[i, "pb"] = y1[lo:hi][m].mean()
            a = ab[lo:hi][m]; a = a[~np.isnan(a)]
            ev.at[i, "pa"] = a.mean() if len(a) else np.nan

cut = {}
dz = ev[ev["cell"] == "설계"]
for metric, col in [("beat", "pb"), ("ab", "pa")]:
    for m in (2, 3):
        ok = ev["pn"] >= m
        thr = dz.loc[dz["pn"] >= m, col].quantile(0.8)
        cut[f"{metric}_m{m}"] = float(thr)
        x = ev[col].where(ok)
        ev[f"s2_{metric}_m{m}"] = np.where(x.notna(), (x >= thr).astype(float), np.nan)
json.dump(cut, open(os.path.join(OUT, "s2_cutoffs.json"), "w"), indent=1)

print("동종 업체 수 분포(설계 칸):", dz["pn"].describe().round(2).to_dict())
print("m>=2 비율:", round((ev["pn"] >= 2).mean(), 3), "m>=3:", round((ev["pn"] >= 3).mean(), 3))
print("cutoffs:", {k: round(v, 4) for k, v in cut.items()})

sigs = ["s2_beat_m2", "s2_beat_m3", "s2_ab_m2", "s2_ab_m3"]
res = run(ev, sigs, "S2", "먼저 발표한 동종 업체 결과가 서프라이즈·반응을 알려주나", "S2")
res.to_csv(os.path.join(OUT, "s2_results.csv"), index=False)
sp = design_splits(ev, sigs)
sp.to_csv(os.path.join(OUT, "s2_design_splits.csv"), index=False)
ev[["t", "date", "rday", "ind", "pn", "pb", "pa"] + sigs].to_csv(os.path.join(DATA, "s2_features.csv"), index=False)

pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(res.drop(columns=["t"]).to_string(index=False))
print("\n설계 칸 분할 참고 (D)")
print(sp.pivot_table(index=["signal", "target"], columns=["split", "value"], values="D").to_string())
