"""과제 2-3-02 (사후 민감도, 결과 본 뒤 추가 — 합격 판정에 쓰지 않음).
원자료 대조에서 '삭감' 중 변동배당·특별배당 혼입·분할 조정 오차가 많이 보여, 10% 이상 삭감만 '진짜 삭감'으로 보는 정의로 다시 본다."""
import os, json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); DV = os.path.join(DATA, "raw", "eodhd", "div"); OUT = os.path.join(ROOT, "task8", "out")
S = pd.read_csv(os.path.join(DATA, "task8_samples.csv"), parse_dates=["date", "exdate"])
E = pd.read_csv(os.path.join(OUT, "decl_events.csv"), parse_dates=["decl"])
G = {}
for t in S["t"].unique():
    d = pd.DataFrame(json.load(open(os.path.join(DV, t.replace(":", "_").replace("/", "_") + ".json"))))
    d = d[(d["currency"].fillna("USD") == "USD") & (d["value"] > 0)].copy(); d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").drop_duplicates("date"); keep, last = [], None
    for i, r in d.iterrows():
        if last is not None and (r["date"] - last).days < 45: continue
        keep.append(i); last = r["date"]
    d = d.loc[keep].reset_index(drop=True); d["ratio"] = d["value"] / d["value"].shift(); d["decl"] = pd.to_datetime(d["declarationDate"], errors="coerce")
    G[t] = d
# 반응: 삭감 크기별
rat = {(t, r.decl): r.ratio for t, d in G.items() for r in d.itertuples() if pd.notna(r.decl)}
E["ratio"] = [rat.get((t, d)) for t, d in zip(E["t"], E["decl"])]
E["chg2"] = pd.cut(E["ratio"], [0, 0.75, 0.9, 0.995, 1.005, 1.10, 99], labels=["삭감≥25%", "삭감10~25%", "삭감<10%", "동일", "증액<10%", "증액≥10%"])
es = E.groupby("chg2", observed=True).agg(n=("car01", "count"), car01_mean=("car01", "mean"), car01_median=("car01", "median"), pre_mean=("carm5m1", "mean"))
es.to_csv(os.path.join(OUT, "sens_event_by_size.csv")); print(es.round(4))
# 엄격한 삭감 목표: 1년 안 10% 이상 삭감 또는 중단(원래 정의의 중단 부분은 그대로: y_cut=1 이면서 삭감<10%만 있는 경우를 0으로)
def strict(r):
    if r.y_cut != 1: return r.y_cut
    d = G[r.t]; fut = d[(d["date"] > r.exdate) & (d["date"] <= r.date + pd.Timedelta(days=365))]
    v0 = d.loc[d["date"] == r.exdate, "value"].iloc[0]
    big = (fut["value"] < v0 * 0.9).any()
    small_only = (fut["value"] < v0 * 0.995).any() and not big
    return 1 if big or not small_only else 0
T = S[S["y_cut"].notna()].copy(); T["y_cut10"] = [strict(r) for r in T.itertuples()]
rows = []
for c in ("설계", "확인1", "확인2", "최종"):
    s = T[T["cell"] == c]
    top = lambda col: s.loc[s[col] >= s.groupby("q")[col].transform(lambda x: x.quantile(0.9)), "y_cut10"].mean()
    rows.append({"cell": c, "events": int(s["y_cut10"].sum()), "base": s["y_cut10"].mean(), "auc_B1": roc_auc_score(s["y_cut10"], s["pB1_y_cut"]),
                 "auc_M": roc_auc_score(s["y_cut10"], s["pM_y_cut"]), "top10_B1": top("pB1_y_cut"), "top10_M": top("pM_y_cut")})
R = pd.DataFrame(rows); R.to_csv(os.path.join(OUT, "sens_cut10.csv"), index=False); print(R.round(4).to_string(index=False))

# 민감도 2: 변동·특별배당 회사 제외 — 전체 이력에서 삭감(<0.995)이 3번 이상인 회사 빼기
ncut = {t: int((d["ratio"] < 0.995).sum()) for t, d in G.items()}
var = {t for t, n in ncut.items() if n >= 3}
E2 = E[~E["t"].isin(var)]
es2 = E2.groupby("chg2", observed=True).agg(n=("car01", "count"), car01_mean=("car01", "mean"), car01_median=("car01", "median"), pre_mean=("carm5m1", "mean"))
es2.to_csv(os.path.join(OUT, "sens_event_novar.csv")); print("variable payers excluded:", len(var)); print(es2.round(4))
rows = []
for c in ("설계", "확인1", "확인2", "최종"):
    s = T[(T["cell"] == c) & ~T["t"].isin(var)]
    top = lambda col: s.loc[s[col] >= s.groupby("q")[col].transform(lambda x: x.quantile(0.9)), "y_cut10"].mean()
    rows.append({"cell": c, "events": int(s["y_cut10"].sum()), "base": s["y_cut10"].mean(), "auc_B1": roc_auc_score(s["y_cut10"], s["pB1_y_cut"]),
                 "auc_M": roc_auc_score(s["y_cut10"], s["pM_y_cut"]), "top10_B1": top("pB1_y_cut"), "top10_M": top("pM_y_cut")})
R2 = pd.DataFrame(rows); R2.to_csv(os.path.join(OUT, "sens_cut10_novar.csv"), index=False); print(R2.round(4).to_string(index=False))
