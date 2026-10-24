"""과제 1-07: S4 공매도 변화, S5 내부자 장내 매수 검정 (PLAN.md §3·§4).

세부 규칙 (실행 전 고정, 2026-10-24):
S4 공매도 변화 (R2 short/volume, FINRA 일별 공매도 거래량, 2010-05~)
- 일별 공매도 비중 = short_vol / total_vol (total_vol > 0).
- 정보 시점 e = 반응일 직전 거래일 (그날 장 마감 뒤 FINRA 공개 → 발표 전 이용 가능).
- 변화 = 평균(비중, e−19..e) ÷ 평균(비중, e−79..e−20). 최근 창 15일·이전 창 45일 이상 있어야 계산.
- 신호: s4_inc = 변화 ≥ 설계 칸 80% 분위 (가설 방향 −: 공매도가 늘면 나쁘다),
        s4_dec = 변화 ≤ 설계 칸 20% 분위 (가설 방향 +: 공매도가 줄면 좋다).
S5 내부자 장내 매수 (R2 sec/insider_hist, 2010~, 코드 P)
- 내부자 = 임원·이사·10% 주주 전체 (이력 파일에 역할 구분이 없음 — 한계로 명시).
- 회사 CIK → 티커: sec/filings 에서 CIK별 가장 많이 쓰인 티커.
- 정보 시점: 공시 접수일(filed) 기준. filed ∈ [반응일−90일, 반응일−1일] 인 P 거래.
- 신호: s5_any = 1건 이상, s5_100k = 매수 금액 합계 ≥ $10만. 대상 기간에 내부자 이력이 있는 이벤트만
  (반응일 ≥ 2010-04-01). 가설 방향 +.
공통: 목표·기준선·판정은 common.py. S4는 반응일 ≥ 2010-09-01 이벤트만. 검정 수 4 × 3 = 12.
"""
import os, json
import numpy as np, pandas as pd
from common import load_events, run, design_splits, OUT, DATA

R2 = os.path.join(DATA, "raw", "r2")
ev = load_events()
ev = ev[ev["rday"].notna()].reset_index(drop=True)

# ---------- S4 ----------
sv = pd.read_parquet(os.path.join(R2, "short_all.parquet"))
sv = sv[sv["total_vol"] > 0]
sv["r"] = sv["short_vol"] / sv["total_vol"]
spy = pd.read_parquet(os.path.join(DATA, "prices", "SPY.parquet"))
cal = spy.index
ev["_pos"] = cal.searchsorted(ev["rday"].values)
chg = np.full(len(ev), np.nan)
svg = {t: g.set_index("date")["r"] for t, g in sv.groupby("ticker")}
for t, g in ev.groupby("t"):
    if t not in svg:
        continue
    r = svg[t].reindex(cal).values
    for pos, i in zip(g["_pos"].values, g.index.values):
        e = pos - 1
        if e - 79 < 0 or g.at[i, "rday"] < pd.Timestamp("2010-09-01"):
            continue
        rec, pri = r[e - 19:e + 1], r[e - 79:e - 19]
        if np.isfinite(rec).sum() < 15 or np.isfinite(pri).sum() < 45:
            continue
        pm = np.nanmean(pri)
        if pm > 0:
            chg[i] = np.nanmean(rec) / pm
ev["s4chg"] = chg
dz = ev[ev["cell"] == "설계"]
lo, hi = dz["s4chg"].quantile([0.2, 0.8])
ev["s4_inc"] = np.where(ev["s4chg"].notna(), (ev["s4chg"] >= hi).astype(float), np.nan)
ev["s4_dec"] = np.where(ev["s4chg"].notna(), (ev["s4chg"] <= lo).astype(float), np.nan)

# ---------- S5 ----------
fl = pd.read_parquet(os.path.join(R2, "sec__filings.parquet"), columns=["cik", "ticker"]).dropna()
cik2t = fl.groupby("cik")["ticker"].agg(lambda x: x.value_counts().index[0])
ih = pd.read_parquet(os.path.join(R2, "sec__insider_hist.parquet"))
ih = ih[ih["code"] == "P"].copy()
ih["t"] = ih["cik"].map(cik2t)
ih = ih.dropna(subset=["t", "filed"])
ih["value"] = ih["value"].fillna(ih["shares"] * ih["price"]).fillna(0)
ihg = {t: g.sort_values("filed")[["filed", "value"]] for t, g in ih.groupby("t")}
any_, amt = np.full(len(ev), np.nan), np.full(len(ev), np.nan)
ok = ev["rday"] >= pd.Timestamp("2010-04-01")
for t, g in ev[ok].groupby("t"):
    h = ihg.get(t)
    for i, rd in zip(g.index.values, g["rday"].values):
        if h is None:
            any_[i], amt[i] = 0.0, 0.0; continue
        f = h["filed"].values
        a = np.searchsorted(f, rd - np.timedelta64(90, "D"), side="left")
        b = np.searchsorted(f, rd - np.timedelta64(1, "D"), side="right")
        v = h["value"].values[a:b].sum()
        any_[i], amt[i] = float(b > a), v
ev["s5_any"] = any_
ev["s5_100k"] = np.where(np.isnan(amt), np.nan, (amt >= 1e5).astype(float))
ev["s5_amt"] = amt

meta = {"s4_cut_20_80": [float(lo), float(hi)], "s4_events": int(ev["s4chg"].notna().sum()),
        "s5_events": int(ev["s5_any"].notna().sum()), "s5_any_share": float(np.nanmean(any_)),
        "s5_100k_share": float(np.nanmean(ev["s5_100k"])), "insider_P_mapped": int(len(ih))}
json.dump(meta, open(os.path.join(OUT, "s4s5_meta.json"), "w"), indent=1)
print(meta)

sigs = ["s4_inc", "s4_dec", "s5_any", "s5_100k"]
res = run(ev, sigs, "S4/S5", "공매도 변화·내부자 매수가 서프라이즈·반응을 알려주나", "S45", neg={"s4_inc"})
res.to_csv(os.path.join(OUT, "s4s5_results.csv"), index=False)
sp = design_splits(ev, sigs)
sp.to_csv(os.path.join(OUT, "s4s5_design_splits.csv"), index=False)
pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format)
print(res.drop(columns=["t"]).to_string(index=False))
print("\n설계 칸 분할 참고 (원래 부호 D)")
print(sp.pivot_table(index=["signal", "target"], columns=["split", "value"], values="D").to_string())
