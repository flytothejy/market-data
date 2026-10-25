"""배당 점검표 (연구 과제 2-3, 과거 비율은 spec 값 그대로)

- 대상: 분기 배당 회사 (정기 배당 간격 중앙값 80~100일). 직전 배당 뒤 45일 안의 배당은 특별배당으로 보고 뺌
  (평소의 2.5배가 넘는 일회성 배당도 특별배당으로 봄 — 연구 규칙에 더한 것)
- 변동배당: 정기 배당이 직전보다 0.5% 넘게 줄어든 적이 3번 이상이면 표시하고 인상·삭감 점검에서 뺌
- 인상 패턴: 다음 예상 배당의 1년 전 무렵 배당이 인상이었으면 '매년 m월경 인상' (과거 77% / 아니면 6%)
- 삭감 점검: 배당수익률(최근 정기 배당 × 4 ÷ 오늘 주가) 절대 구간 × 지난 1년 시장 대비 −20% 이하 여부
배당 금액은 가격 수집 기록(분할 반영) 그대로 — 오늘 주가와 같은 기준이라 오늘 배당수익률 계산에는 문제없음
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

SPEC_P = Path(__file__).resolve().parent / "spec" / "tickermap_spec.json"
_S = None


def spec():
    global _S
    if _S is None:
        _S = json.loads(SPEC_P.read_text(encoding="utf-8"))
    return _S


def bucket(y):
    return "<2%" if y < 0.02 else "2-4%" if y < 0.04 else "4-6%" if y < 0.06 else ">=6%"


def check(ac, px, ret_rel=None, pe=None, today=None):
    """ac: 한 종목 actions(date·dividend), px: 오늘 종가, ret_rel: 지난 1년 시장 대비 수익률 → dict 또는 None"""
    if ac is None or not len(ac) or not px:
        return None
    d = ac[ac.dividend > 0].sort_values("date")
    if len(d) < 4:
        return None
    today = pd.Timestamp(today or pd.Timestamp.now().normalize())
    dates, amt = pd.to_datetime(d.date).tolist(), d.dividend.astype(float).tolist()
    reg = []                                             # 정기 배당 (특별배당 제외)
    for t, a in zip(dates, amt):
        if reg and (t - reg[-1][0]).days < 45:
            continue
        prev = [x[1] for x in reg[-4:]]
        if len(prev) >= 3 and a > 2.5 * float(np.median(prev)):   # 평소의 2.5배 넘는 일회성 배당(COST 등)도 특별배당
            continue
        reg.append((t, a))
    if len(reg) < 4 or (today - reg[-1][0]).days > 200:  # 배당이 끊긴 회사
        return None
    gaps = [(reg[i][0] - reg[i - 1][0]).days for i in range(1, len(reg))]
    med = float(np.median(gaps[-12:]))
    out = {"last": reg[-1][1], "last_d": str(reg[-1][0].date()), "since": str(reg[0][0].date())[:4], "q": 80 <= med <= 100}
    if not out["q"]:
        return out
    chg = [(reg[i][0], reg[i][1] / reg[i - 1][1] - 1) for i in range(1, len(reg))]
    cuts = [t for t, r in chg if r < -0.005]
    ups = [(t, r) for t, r in chg if r > 0.005]
    out["var"] = len(cuts) >= 3
    out["cut_d"] = str(cuts[-1].date()) if cuts else None
    if ups:
        out["up"], out["up_d"] = round(ups[-1][1], 4), str(ups[-1][0].date())
    y = reg[-1][1] * 4 / px
    out["yld"] = round(y, 4)
    if pe and pe > 0:
        out["payout"] = round(y * pe, 3)                 # 배당성향 = 배당수익률 ÷ 이익수익률
    if ret_rel is not None:
        out["ret_rel"] = round(ret_rel, 4)
    if out["var"]:
        return out
    S = spec()["dividend"]
    nxt = reg[-1][0] + pd.Timedelta(days=med)
    ref = nxt - pd.Timedelta(days=365)
    near = [(t, r) for t, r in chg if abs((t - ref).days) <= 45]
    if near:
        t0, r0 = min(near, key=lambda x: abs((x[0] - ref).days))
        out["anniv"] = bool(r0 > 0.005)
        if out["anniv"]:
            out["anniv_m"] = int(t0.month)
    b = bucket(y)
    weak = ret_rel is not None and ret_rel <= -0.20
    out["bucket"], out["weak"] = b, weak
    out["cut_rate"] = S["cut_1y_by_yield_large_and_ret1y_le_-20pct"][b] if weak else S["cut_1y_by_yield_large"][b]
    return out
