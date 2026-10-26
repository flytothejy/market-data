"""부실 위험 등급 (연구 과제 2-5, research 브랜치 → hub/spec/tickermap_spec.json 값을 그대로 씀)

- 대상: 미국 본사, 비금융·비부동산, 직전 252거래일 평균 거래대금 2천만 달러 이상
- 점수 p = 1/(1+e^-logit), logit = const + Σ b·x + Σ b_m·m (재무 변수·exret 결측만 중앙값 + 결측 표시)
- 변동성·주가·시가총액이 없으면 등급 없이 '산출 불가' (m_sigma·m_rsize 계수는 쓰지 않음)
- 등급은 p의 고정 기준값으로 자름 (집단 안 순위 아님). 화면에는 p를 쓰지 않음
- 시가총액은 시세 정보 값이 1순위 (분할 반영 가격으로 만든 과거 시가총액은 쓰지 않음)
"""
import json, math
from pathlib import Path

import numpy as np
import pandas as pd

SPEC_P = Path(__file__).resolve().parent / "spec" / "tickermap_spec.json"
VARS = ["nz", "nimta", "tlmta", "cashmta", "exret", "sigma", "rsize", "price"]
IMPUTE = ["nz", "nimta", "tlmta", "cashmta", "exret"]          # 결측이면 중앙값 + m_ 계수
REQUIRED = ["sigma", "price", "rsize"]                           # 없으면 산출 불가
GRADES = ["보통", "주의", "높음", "매우 높음"]                     # 화면 값: 0~3
FIN_SECTORS = {"Financial Services", "Real Estate", "Financials"}
# 근거 칩: 대상 종목 중 위험 쪽 상위 20%면 켬 (변수, 방향 +1=클수록 위험)
CHIPS = [("sigma", 1, "vol", "변동성 높음"), ("tlmta", 1, "debt", "부채 비율 높음"), ("price", -1, "px", "주가 낮음"),
         ("nimta", -1, "loss", "적자"), ("exret", -1, "ret", "1년 수익률 부진")]


def spec():
    return json.loads(SPEC_P.read_text(encoding="utf-8"))


def _f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def unadjusted(g, splits):
    """F4: 분할 반영 종가 → 그날의 실제 주가. 실제 = close × (그날 이후 분할 비율의 곱)
    g: date·close 프레임(한 종목), splits: date·split 프레임(같은 종목, split>0)"""
    c = g.close.astype(float).values.copy()
    if splits is None or not len(splits):
        return pd.Series(c, index=g.index)
    d = pd.to_datetime(g.date).values
    for sd, r in zip(pd.to_datetime(splits.date).values, splits.split.astype(float).values):
        if r and r > 0 and r != 1:
            c[d < sd] *= r
    return pd.Series(c, index=g.index)


def inputs(fm, mcap, g, spy, px_today):
    """한 종목의 입력값 dict (없는 값은 None). fm: build.fin_metrics 결과, g/spy: 가격 프레임(date·close·adj_close·volume)"""
    A, L = _f(fm.get("_assets")), _f(fm.get("_liab_d") if "_liab_d" in fm else fm.get("_liab"))   # 총부채: 미보고 시 파생값
    ca, cl, re_, cash = _f(fm.get("_ca")), _f(fm.get("_cl")), _f(fm.get("_re")), _f(fm.get("_cash"))
    opi, ni, rev = _f(fm.get("_opi_ttm")), _f(fm.get("ni")), _f(fm.get("rev"))
    mcap = _f(mcap)
    x = {k: None for k in VARS}
    if A and A > 0 and L and L > 0 and mcap and None not in (ca, cl, re_, opi, rev):
        z = 1.2 * (ca - cl) / A + 1.4 * re_ / A + 3.3 * opi / A + 0.6 * mcap / L + 1.0 * rev / A
        x["nz"] = -z
    if mcap and L is not None and L >= 0:
        den = mcap + L
        if ni is not None:
            x["nimta"] = ni / den
        x["tlmta"] = L / den
        if cash is not None:
            x["cashmta"] = cash / den
    if mcap and mcap > 0:
        x["rsize"] = math.log(mcap)
    if px_today and px_today > 0:
        x["price"] = math.log(min(px_today, 15.0))
    if g is not None and len(g) >= 64:
        a = g.adj_close.astype(float).values
        lr = np.diff(np.log(a[-64:]))
        if np.all(np.isfinite(lr)):
            x["sigma"] = float(np.std(lr, ddof=1))
    if g is not None and spy is not None and len(g) >= 253:
        m = pd.merge(g[["date", "adj_close"]].tail(253), spy[["date", "adj_close"]], on="date", suffixes=("", "_m"))
        if len(m) >= 240:
            r = math.log(m.adj_close.iloc[-1] / m.adj_close.iloc[0]) - math.log(m.adj_close_m.iloc[-1] / m.adj_close_m.iloc[0])
            x["exret"] = r if math.isfinite(r) else None
    return x


def score(x, S=None):
    """→ (p 또는 None, 결측·산출 불가 사유 list)"""
    S = S or spec()["distress"]
    flags = [f"없음:{k}" for k in REQUIRED if x.get(k) is None]
    if flags:
        return None, flags
    b, lo_hi, med = S["coef"], S["clip"], S["median"]
    lg = b["const"]
    for k in VARS:
        v = x.get(k)
        if v is None:                                    # IMPUTE 변수만 여기 옴
            lg += b[k] * med[k] + b["m_" + k]
            flags.append(f"중앙값:{k}")
        else:
            lo, hi = lo_hi[k]
            lg += b[k] * min(max(v, lo), hi)
    return 1 / (1 + math.exp(-lg)), flags


def grade(p, S=None):
    if p is None:
        return None
    th = (S or spec()["distress"])["grade_thresholds_p"]
    return 3 if p >= th["매우 높음"] else 2 if p >= th["높음"] else 1 if p >= th["주의"] else 0


def eligible(country, sector, adv):
    if country != "United States":
        return False, "미국 본사 아님"
    if sector in FIN_SECTORS:
        return False, "금융·부동산"
    if adv is None or adv < 2e7:
        return False, "거래대금 2천만 달러 미만"
    return True, None


def run(cands, asof, out_dir=None):
    """cands: [{t, cik, mcap, country, sector, adv, x(inputs)}] → ({t: {g, c:[칩]}}, research_live 기록 dict)"""
    sp = spec()
    S = sp["distress"]
    rows, res, scored = [], {}, []
    for c in cands:
        ok, why = eligible(c.get("country"), c.get("sector"), c.get("adv"))
        p, flags = (score(c["x"], S) if ok else (None, [why]))
        g = grade(p, S) if ok else None
        rows.append({"ticker": c["t"], "cik": c.get("cik"), "mcap": c.get("mcap"), "inputs": {k: c["x"].get(k) for k in VARS},
                     "score": p, "grade": GRADES[g] if g is not None else None, "flags": flags})
        if g is not None:
            scored.append((c, g))
            res[c["t"]] = {"g": g, "c": []}
    # 근거 칩: 등급이 매겨진 종목 안에서 위험 쪽 상위 20%
    if scored:
        X = pd.DataFrame([{**{k: s[0]["x"].get(k) for k in VARS}, "t": s[0]["t"]} for s in scored]).set_index("t")
        for var, sign, code, _ in CHIPS:
            col = X[var].dropna() * sign
            if len(col) < 20:
                continue
            cut = col.quantile(0.8)
            sel = col[col >= cut]
            if len(sel) > 0.25 * len(col):                 # 같은 값이 몰리면(주가는 15달러에서 잘림) 경계값은 빼고
                sel = col[col > cut]
            if var == "price":                             # '주가 낮음'은 실제로 15달러 미만일 때만
                sel = sel[X.loc[sel.index, "price"] < math.log(15) - 1e-9]
            for t in sel.index:
                if var == "nimta" and X.at[t, "nimta"] >= 0:   # '적자'는 실제로 순손실일 때만
                    continue
                res[t]["c"].append(code)
    live = {"date": asof, "spec_version": sp["version"], "n_universe": sum(1 for r in rows if r["score"] is not None), "rows": rows}
    if out_dir:
        p = Path(out_dir) / "distress" / f"{asof}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(live, ensure_ascii=False, default=lambda o: None if o is None else float(o)), encoding="utf-8")
    return res, live
