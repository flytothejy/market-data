"""생존편향 2: 편향 크기 측정.

매년 첫 거래일의 실제 S&P 500 구성 종목(sp500_hist.csv) 중
 - 우리 가격 데이터가 있는 종목(같은 회사의 현재 티커로 연결된 경우 포함)만으로 만든 동일가중 1년 수익률(생존자 포트폴리오)과
 - 동일가중 S&P 500 ETF RSP의 1년 수익률(상장폐지·편출 종목을 실제로 담았던 포트폴리오)
을 비교한다. 차이 = 그해 생존편향이 수익률을 부풀린 크기(근사).
또 그해 구성 종목 중 우리 데이터에 없는 비율과 그 사유 구성을 함께 낸다.
한계: RSP는 분기 리밸런싱·보수 0.2%, 우리는 연초 동일가중 보유. 연중 신규 편입 종목은 양쪽 모두 무시.
"""
import os, json
import numpy as np, pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "data", "raw", "sb")
PX = os.path.join(ROOT, "data", "prices")
OUT = os.path.join(ROOT, "survivorship", "out")

h = pd.read_csv(os.path.join(SB, "sp500_hist.csv"), parse_dates=["date"])
cls = pd.read_csv(os.path.join(OUT, "gone_classified.csv"))
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cik2now = dict(zip(cur["cik_str"], cur["ticker"].str.replace(".", "-", regex=False)))
alias = {}
for _, r in cls[cls["class"] == "같은 회사(이름·티커 변경)"].iterrows():
    for x in str(r.get("tickers_now") or "").split(","):
        if x and os.path.exists(os.path.join(PX, f"{x.replace('.', '-')}.parquet")):
            alias[r["t"]] = x.replace(".", "-"); break
    else:
        try:
            n = cik2now.get(int(r["cik"]))
            if n and os.path.exists(os.path.join(PX, f"{n}.parquet")):
                alias[r["t"]] = n
        except (TypeError, ValueError):
            pass
cmap = dict(zip(cls["t"], cls["class"]))
# 가격 파일이 없는 구성 종목: 위키백과 과거 판본의 CIK → SEC 현재 티커로 연결 (최근 티커 변경)
wm = pd.read_csv(os.path.join(SB, "wiki_members_hist.csv")).dropna(subset=["cik"])
for t, c in wm.groupby("t")["cik"].first().items():
    t2 = str(t).replace(".", "-")
    if t2 in alias or os.path.exists(os.path.join(PX, f"{t2}.parquet")):
        continue
    n = cik2now.get(int(c))
    if n and n != t2 and os.path.exists(os.path.join(PX, f"{n}.parquet")):
        alias[t2] = n
print("현재 티커로 연결:", len(alias), {k: v for k, v in list(alias.items())[:40]})

rsp = yf.download("RSP", start="2005-12-01", auto_adjust=True, progress=False)["Close"].squeeze()
cache = {}
def px(t):
    t = t.replace(".", "-"); t2 = alias.get(t, t)
    if t2 not in cache:
        p = os.path.join(PX, f"{t2}.parquet")
        cache[t2] = pd.read_parquet(p)["Close"] if os.path.exists(p) else None
    return cache[t2]

rows = []
for y in range(2006, 2026):
    d0 = h[h["date"].dt.year == y]["date"].min()
    mem = h.loc[h["date"] == d0, "tickers"].iloc[0].split(",")
    s, e = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
    r_rsp = rsp[s:e].iloc[-1] / rsp[:s].iloc[-1] - 1
    rets, miss = [], {}
    for t in mem:
        p = px(t)
        if p is None or p[s:e].empty or p[:s].empty:
            k = cmap.get(t, "기타(데이터 없음)")
            miss[k] = miss.get(k, 0) + 1
            continue
        a, b = p[:s].iloc[-1], p[s:e].iloc[-1]
        if p[s:e].index[-1] < e - pd.Timedelta(days=10):      # 연중 거래 중단 → 생존자 아님
            k = cmap.get(t, "기타(중간 중단)"); miss[k] = miss.get(k, 0) + 1; continue
        rets.append(b / a - 1)
    rows.append({"year": y, "members": len(mem), "have": len(rets), "missing": len(mem) - len(rets),
                 "missing_pct": (len(mem) - len(rets)) / len(mem), "survivor_ew": np.mean(rets), "rsp": r_rsp,
                 "bias": np.mean(rets) - r_rsp, **{f"m_{k}": v for k, v in miss.items()}})
df = pd.DataFrame(rows).fillna(0)
df.to_csv(os.path.join(OUT, "bias_by_year.csv"), index=False)
pd.set_option("display.width", 250, "display.float_format", "{:.3f}".format)
print(df[["year", "members", "missing", "missing_pct", "survivor_ew", "rsp", "bias"]].to_string(index=False))
print("\n평균 연 편향 %.2f%%p, 2006-09 평균 %.2f%%p, 2010-25 평균 %.2f%%p" % (
    100 * df.bias.mean(), 100 * df[df.year <= 2009].bias.mean(), 100 * df[df.year >= 2010].bias.mean()))
mc = [c for c in df.columns if c.startswith("m_")]
print("\n없는 종목 사유 합계:", df[mc].sum().astype(int).sort_values(ascending=False).to_dict())
