"""EODHD 상장폐지 가격 정리 (2026-10-25, 과제 2·1 재검증 결과를 본 뒤 발견한 오류 대응).
1) 튀는 값: 앞뒤 5거래일(자기 제외) 중앙값 대비 3배 초과 또는 1/3 미만인 날은 비움 (예: TRA 18,038→1.69→18,883)
2) 단위 바뀜: 남은 값에서 하루 10배 이상 변화가 있으면 그날부터 잘라냄(그 전에서 현금 처리) (예: SPM 40→35,700 계속)
출력: research/data/prices_delisted_clean/{CODE}.parquet, 정리 로그
"""
import os, glob
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "prices_delisted"); DST = os.path.join(ROOT, "data", "prices_delisted_clean")
os.makedirs(DST, exist_ok=True)
log = []
for p in glob.glob(os.path.join(SRC, "*.parquet")):
    dst = os.path.join(DST, os.path.basename(p))
    if os.path.exists(dst) and os.environ.get("RESUME") == "1":
        x0 = pd.read_parquet(p).groupby(level=0).last(); y0 = pd.read_parquet(dst)   # 이미 처리됨: 로그만 다시 계산
        n_sp = int((x0["Close"].reindex(y0.index).notna() & y0["Close"].isna()).sum())
        cut0 = len(y0) < len(x0) and y0.index.max() < x0.index.max()
        if n_sp or cut0: log.append((os.path.basename(p)[:-8], n_sp, str(y0.index.max().date()) if cut0 else ""))
        continue
    x = pd.read_parquet(p).groupby(level=0).last()
    c = x["Close"].where(x["Close"] > 0)
    v = c.values.astype(float); n = len(v); spike = np.zeros(n, bool)
    for i in range(n):
        if not np.isfinite(v[i]): continue
        w = np.r_[v[max(0, i - 5):i], v[i + 1:i + 6]]; w = w[np.isfinite(w)]
        if len(w) >= 4:
            m = np.median(w)
            if v[i] > 3 * m or v[i] < m / 3: spike[i] = True
    c2 = c.copy(); c2[spike] = np.nan
    r = np.log(c2 / c2.ffill().shift(1)).abs()
    cut = r[r > np.log(10)].index.min()
    keep = x.index < cut if pd.notna(cut) else np.ones(n, bool)
    y = x.copy()
    for col in ("Close", "RawClose", "RawUnadj"):
        if col in y: y.loc[spike, col] = np.nan
    y = y[keep]
    y.to_parquet(os.path.join(DST, os.path.basename(p)))
    if spike.any() or pd.notna(cut):
        log.append((os.path.basename(p)[:-8], int(spike.sum()), str(cut.date()) if pd.notna(cut) else ""))
pd.DataFrame(log, columns=["code", "spikes_removed", "truncated_from"]).to_csv(os.path.join(ROOT, "survivorship", "out", "clean_delisted_log.csv"), index=False)
print("files", len(glob.glob(os.path.join(SRC, "*.parquet"))), "changed", len(log),
      "truncated", sum(1 for l in log if l[2]))
