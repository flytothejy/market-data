"""화면용 데이터 만들기 — data/hub 원자료 → data/hub/site/api/v1/...

  free/universe.json        종목·ETF 한 줄 요약 (다섯 카테고리 지표) + 지표 사전
  free/stock/{T}.json       종목 상세 (차트·재무 5년·공시·내부자·공매도·옵션·뉴스·ETF 편입·13F)
  pro/stock/{T}.json        프로 전용 (재무 전체 이력, 10-K 새 위험 문장)
  free/etf/{T}.json         ETF 상세 (구성·섹터·배당·가격)
  free/kr_etf.json, free/kr_etf/{code}.json   국내 상장 미국 ETF
  free/market.json          시장 요약 (업종별 중앙값, 200일선 위 비율, 지수)
  meta.json                 생성 시각, 수집기별 상태, 개수
화면은 이 파일들만 읽음 → 나중에 Cloudflare/Supabase로 옮겨도 같은 주소·형식 유지
"""
import json, math, os, re, shutil, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd

from .core import DATA, ROOT, Run, log, read, load_status
from .fields import F as FIELDS, CATS
from . import universe as uni

OUT = DATA / "site" / "api" / "v1"
ITEMS_8K = {"1.01": "중요 계약", "1.02": "계약 해지", "1.03": "파산", "1.05": "사이버 사고", "2.01": "인수·매각 완료", "2.02": "실적 발표",
            "2.03": "채무 발생", "2.05": "구조조정", "2.06": "자산 손상", "3.01": "상장 요건", "3.02": "증권 발행", "4.01": "감사인 변경",
            "4.02": "재무제표 정정", "5.01": "지배권 변경", "5.02": "임원 변동", "5.03": "정관 변경", "5.07": "주총 결과", "7.01": "공정 공시",
            "8.01": "기타 사건"}


# ---------------------------------------------------------------- 공통
def clean(o, nd=4):
    """JSON용: NaN/inf → None, float 반올림, numpy → 파이썬"""
    if isinstance(o, dict):
        out = {k: clean(v, nd) for k, v in o.items()}
        return {k: v for k, v in out.items() if v is not None}
    if isinstance(o, (list, tuple)):
        return [clean(v, nd) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        if not math.isfinite(f):
            return None
        a = abs(f)
        return round(f, nd if a < 10 else 2 if a < 1e5 else 0)
    if isinstance(o, (pd.Timestamp, dt.date, dt.datetime)):
        return str(o)[:10]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    try:
        if pd.isna(o):
            return None
    except (TypeError, ValueError):
        pass
    return str(o)


def dump(path, obj, nd=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj, nd), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def nz(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def div(a, b):
    try:
        return a / b if a is not None and b not in (None, 0) and math.isfinite(a) and math.isfinite(b) else None
    except Exception:
        return None


# ---------------------------------------------------------------- 재무 표준화
REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
       "SalesRevenueNet", "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue", "ElectricUtilityRevenue",
       "OperatingLeasesIncomeStatementLeaseRevenue", "Revenue", "RevenueFromContractsWithCustomers"]
CONCEPTS = {
    "gp": ["GrossProfit"], "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "opi": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "ni": ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "eps": ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare", "EarningsPerShareBasic"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "rnd": ["ResearchAndDevelopmentExpense"], "buyback": ["PaymentsForRepurchaseOfCommonStock"],
    "divpaid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"], "sbc": ["ShareBasedCompensation"],
    "nii": ["InterestIncomeExpenseNet"], "nonii": ["NoninterestIncome"],
}
BAL = {"assets": ["Assets"], "liab": ["Liabilities"], "equity": ["StockholdersEquity", "Equity"],
       "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], "ltd": ["LongTermDebtNoncurrent", "LongTermDebt"],
       "ca": ["AssetsCurrent"], "cl": ["LiabilitiesCurrent"], "shares": ["EntityCommonStockSharesOutstanding"]}


def _latest(df):
    return df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")


def flow_series(df):
    """흐름 항목 → (분기별 dict end→값, 연간 dict end→값). 누적(3·6·9·12개월) 값에서 분기를 역산"""
    if df is None or df.empty:
        return {}, {}
    d = _latest(df.dropna(subset=["start_dt"]))
    if d.empty:
        return {}, {}
    st = d.start_dt.values.astype("datetime64[D]")
    en = d.end_dt.values.astype("datetime64[D]")
    vals = d.val.values.astype(float)
    days = (en - st).astype(int)
    E = [pd.Timestamp(x) for x in en]
    annual = {E[i]: vals[i] for i in np.where((days >= 350) & (days <= 380))[0]}
    k_arr = np.rint(days / 91.3).astype(int)
    okq = (k_arr >= 1) & (k_arr <= 4) & (np.abs(days - k_arr * 91.3) <= 12)
    q = {}
    by_start = {}
    for i in np.where(okq)[0]:
        by_start.setdefault(st[i], {})[k_arr[i]] = i
    for cum in by_start.values():
        for k in range(1, 5):
            if k in cum and (k == 1 or (k - 1) in cum):
                q[E[cum[k]]] = vals[cum[k]] - (vals[cum[k - 1]] if k > 1 else 0)
    for i in np.where((days >= 80) & (days <= 100))[0]:        # 3개월 값이 직접 있으면 우선
        q[E[i]] = vals[i]
    out = {}
    for e in sorted(q):
        if out and (e - max(out)).days < 10:
            out.pop(max(out))
        out[e] = q[e]
    return out, annual


def ttm(qs, back=0):
    ks = sorted(qs)
    if len(ks) < 4 + back:
        return None
    sel = ks[len(ks) - 4 - back: len(ks) - back]
    span = (sel[-1] - sel[0]).days
    return sum(qs[k] for k in sel) if 250 <= span <= 300 else None


def pick(G, tags, unit_pref=("USD", "USD/shares", "shares")):
    """후보 태그 중 가장 최근 값이 있는 태그·단위 (G: 태그→DataFrame dict)"""
    best, best_end = None, None
    for t in tags:
        g = G.get(t)
        if g is None or g.empty:
            continue
        units = g.unit.value_counts().index.tolist()
        u = next((x for x in unit_pref if x in units), units[0])
        g = g[g.unit == u]
        e = g.end_dt.max()
        if best_end is None or e > best_end + pd.Timedelta(days=30):
            best, best_end = g, e
    return best if best is not None else EMPTY


EMPTY = pd.DataFrame(columns=["tag", "unit", "start", "end", "val", "filed", "accn", "end_dt", "start_dt"])


def fin_company(G0):
    G = dict(tuple(G0.groupby("tag")))
    gmax = G0.end_dt.max()
    res = {"q": {}, "a": {}}
    rv = pick(G, REV)
    cur = (rv.unit.iloc[0] if len(rv) else "USD")
    qs, an = flow_series(rv)
    # 은행: 순이자이익 + 비이자이익
    if len(rv) == 0 or (rv.end_dt.max() < gmax - pd.Timedelta(days=200)):
        q1, a1 = flow_series(pick(G, CONCEPTS["nii"]))
        q2, a2 = flow_series(pick(G, CONCEPTS["nonii"]))
        if q1 and q2:
            qs = {k: q1[k] + q2[k] for k in q1 if k in q2}
            an = {k: a1[k] + a2[k] for k in a1 if k in a2}
    res["q"]["rev"], res["a"]["rev"] = qs, an
    for c, tags in CONCEPTS.items():
        if c in ("nii", "nonii"):
            continue
        res["q"][c], res["a"][c] = flow_series(pick(G, tags))
    if not res["q"]["gp"] and res["q"]["cogs"]:
        res["q"]["gp"] = {k: res["q"]["rev"][k] - v for k, v in res["q"]["cogs"].items() if k in res["q"]["rev"]}
        res["a"]["gp"] = {k: res["a"]["rev"][k] - v for k, v in res["a"]["cogs"].items() if k in res["a"]["rev"]}
    bal = {}
    for c, tags in BAL.items():
        g = pick(G, tags)
        g = g[g.start_dt.isna()] if len(g) else g
        if len(g):
            g = g.sort_values(["end_dt", "filed"])
            last = g[g.end_dt == g.end_dt.max()]
            bal[c] = float(last.drop_duplicates("accn", keep="last").groupby("accn").val.sum().iloc[-1]) if c == "shares" else float(last.val.iloc[-1])
            bal[c + "_date"] = g.end_dt.max()
    res["bal"], res["cur"] = bal, cur
    return res


def fin_metrics(fc):
    Q, B = fc["q"], fc["bal"]
    T = {c: ttm(Q[c]) for c in Q}
    P = {c: ttm(Q[c], back=4) for c in Q}
    rq = Q["rev"]
    ks = sorted(rq)
    rev_qg = None
    if len(ks) >= 5:
        last = ks[-1]
        prev = [k for k in ks if 350 <= (last - k).days <= 380]
        if prev:
            rev_qg = div(rq[last], rq[prev[-1]]) - 1 if div(rq[last], rq[prev[-1]]) else None
    m = {"rev": T["rev"], "rev_g": (div(T["rev"], P["rev"]) - 1) if div(T["rev"], P["rev"]) else None, "rev_qg": rev_qg,
         "gm": div(T["gp"], T["rev"]), "om": div(T["opi"], T["rev"]), "nm": div(T["ni"], T["rev"]), "ni": T["ni"],
         "ni_g": (div(T["ni"], P["ni"]) - 1) if (P["ni"] or 0) > 0 and div(T["ni"], P["ni"]) else None, "eps": T["eps"],
         "fcf": (T["cfo"] - T["capex"]) if T["cfo"] is not None and T["capex"] is not None else T["cfo"],
         "roe": div(T["ni"], B.get("equity")) if (B.get("equity") or 0) > 0 else None, "roa": div(T["ni"], B.get("assets")),
         "de": div(B.get("ltd"), B.get("equity")) if (B.get("equity") or 0) > 0 else None, "cr": div(B.get("ca"), B.get("cl")),
         "rnd": div(T["rnd"], T["rev"]), "fq": max(ks) if ks else None, "cur": fc["cur"],
         "_buyback": T["buyback"], "_divpaid": T["divpaid"], "_equity": B.get("equity"), "_shares": B.get("shares")}
    om0 = div(P["opi"], P["rev"])
    m["om_chg"] = (m["om"] - om0) if m["om"] is not None and om0 is not None else None
    return m


def fin_tables(fc, n_a=15, n_q=12):
    """차트용 연간·분기 표"""
    def table(src, keys, n):
        ends = sorted(set().union(*[set(src[k]) for k in keys if src.get(k)]))[-n:]
        return [{"end": e, **{k: src[k].get(e) for k in keys if src.get(k)}} for e in ends]
    keys = ["rev", "gp", "opi", "ni", "eps", "cfo", "capex", "rnd", "buyback", "divpaid"]
    return table(fc["a"], keys, n_a), table(fc["q"], keys, n_q)


# ---------------------------------------------------------------- 가격·기술 지표
def tech(g):
    c = g.close.values.astype(float)
    a = g.adj_close.values.astype(float)
    v = g.volume.values.astype(float)
    if len(a) < 30:
        return {}
    d = g.date.values
    def ret(n):
        return a[-1] / a[-1 - n] - 1 if len(a) > n and a[-1 - n] > 0 else None
    s = pd.Series(a)
    dl = s.diff()
    up = dl.clip(lower=0).ewm(alpha=1 / 14).mean()
    dn = (-dl.clip(upper=0)).ewm(alpha=1 / 14).mean()
    rsi = float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])) if dn.iloc[-1] > 0 else None
    sma50, sma200 = s.rolling(50).mean(), s.rolling(200).mean()
    gc = None
    if len(s) > 200:
        x = (sma50 > sma200).astype(int).diff()
        idx = np.where(x.values == 1)[0]
        gc = pd.Timestamp(d[idx[-1]]) if len(idx) else None
    yr = pd.Timestamp(d[-1]).year
    ystart = np.where(pd.to_datetime(d).year < yr)[0]
    w = a[-252:]
    return {"px": c[-1], "r1d": ret(1), "r1w": ret(5), "r1m": ret(21), "r3m": ret(63), "r6m": ret(126), "r1y": ret(252),
            "rytd": a[-1] / a[ystart[-1]] - 1 if len(ystart) else None,
            "r12_1": a[-22] / a[-253] - 1 if len(a) > 253 else None,
            "d50": a[-1] / sma50.iloc[-1] - 1 if len(a) >= 50 else None, "d200": a[-1] / sma200.iloc[-1] - 1 if len(a) >= 200 else None,
            "rsi": rsi, "hi52": a[-1] / w.max() - 1, "lo52": a[-1] / w.min() - 1,
            "vr": v[-20:].mean() / v[-120:].mean() if v[-120:].mean() > 0 else None,
            "vol": float(np.std(np.diff(np.log(a[-61:]))) * np.sqrt(252)) if len(a) > 61 else None, "gc": gc,
            "asof": pd.Timestamp(d[-1])}



# ---------------------------------------------------------------- 종목 한 줄 요약 (규칙 기반, 토큰 0)
def _p(x, sign=True):
    v = x * 100
    return (("+" if sign and v > 0 else "") + (f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}")) + "%"


def _usd(v):
    a = abs(v)
    return f"${a/1e12:.1f}조" if a >= 1e12 else f"${a/1e8:,.0f}억" if a >= 1e8 else f"${a/1e4:,.0f}만"


def summary_line(r, today):
    """지표에서 눈에 띄는 것만 골라 개조식 한 줄. (문구, 극성 +1/-1/0, 중요도)를 모아 상위만 씀
    나중에 LLM 요약이 붙으면 같은 자리(s1)를 대체하고, 검사에 실패하면 이 문장이 남는다"""
    g = lambda k: r.get(k)
    C = []
    add = lambda txt, pol, w: C.append((txt, pol, w))
    if r.get("k") == "etf":
        if g("hi52") is not None and g("hi52") >= -0.01: add("52주 신고가", 1, 3)
        elif g("hi52") is not None and g("hi52") <= -0.2: add(f"고점 대비 {_p(g('hi52'))}", -1, 3)
        if g("r1m") is not None: add(f"1개월 {_p(g('r1m'))}", 1 if g("r1m") > 0 else -1, 1 + abs(g("r1m")) * 10)
        if g("dy") and g("dy") >= 0.03: add(f"배당수익률 {_p(g('dy'), False)}", 1, 1.5)
        if g("exp") is not None: add(f"총보수 {g('exp')*100:.2f}%", 0, 1)
    else:
        rg, oc = g("rev_g"), g("om_chg")
        if rg is not None:
            if rg >= 1: add(f"매출 {rg + 1:.1f}배로 급증", 1, 4)
            elif rg >= 0.25: add(f"매출 {_p(rg)} 고성장", 1, 2 + rg * 3)
            elif rg >= 0.1: add(f"매출 {_p(rg)} 성장", 1, 1.5)
            elif rg < -0.05: add(f"매출 {_p(rg)} 감소", -1, 2 + abs(rg) * 3)
        if oc is not None and abs(oc) >= 0.04:
            add(f"영업이익률 {'개선' if oc > 0 else '하락'}({oc*100:+.1f}%p)", 1 if oc > 0 else -1, 1.5 + abs(oc) * 10)
        if g("c_n") and g("c_ratio") is not None and abs(g("c_ratio")) >= 0.2:
            add(f"애널리스트 전망 {'상향' if g('c_ratio') > 0 else '하향'} 우세", 1 if g("c_ratio") > 0 else -1, 2 + abs(g("c_ratio")) * 3)
        if g("c_n") and (g("c_upside") or 0) >= 0.3:
            add(f"평균 목표가까지 {_p(g('c_upside'), False)} 여력", 1, 1.5)
        if (g("ibn") or 0) >= 2: add(f"내부자 {int(g('ibn'))}명 장내 매수", 1, 3 + g("ibn") * 0.3)
        elif (g("ib") or 0) > 0: add(f"내부자 장내 매수 {_usd(g('ib'))}", 1, 2)
        elif (g("is") or 0) >= 5e7: add(f"90일 내부자 매도 {_usd(g('is'))}", -1, 1.2)
        if (g("k8") or 0) >= 3: add(f"30일간 8-K {g('k8')}건", 0, 1.5)
        pe = g("pe")
        if pe and pe >= 60: add(f"PER {pe:.0f}배로 높은 편", -1, 1.2)
        elif pe and 0 < pe <= 12: add(f"PER {pe:.0f}배로 낮은 편", 1, 1.2)
        if (g("dy") or 0) >= 0.035: add(f"배당수익률 {_p(g('dy'), False)}", 1, 1.3)
        if (g("si") or 0) >= 0.1: add(f"공매도 잔고 {_p(g('si'), False)}", -1, 1.5 + g("si") * 5)
        elif (g("sv_chg") or 0) >= 0.08: add("공매도 거래 비중 상승", -1, 1.4)
        h52, r1m = g("hi52"), g("r1m")
        if h52 is not None and h52 >= -0.01: add("52주 신고가", 1, 2.5)
        elif h52 is not None and h52 <= -0.35: add(f"고점 대비 {_p(h52)}", -1, 2 + abs(h52) * 2)
        if r1m is not None and abs(r1m) >= 0.12: add(f"1개월 {_p(r1m)} {'급등' if r1m > 0 else '급락'}", 1 if r1m > 0 else -1, 2 + abs(r1m) * 5)
        if (g("vr") or 0) >= 1.5: add(f"거래량 {g('vr'):.1f}배", 0, 1.2)
    pos = sorted([c for c in C if c[1] > 0], key=lambda c: -c[2])
    neg = sorted([c for c in C if c[1] < 0], key=lambda c: -c[2])
    neu = sorted([c for c in C if c[1] == 0], key=lambda c: -c[2])
    if pos and neg:
        txt = ", ".join(c[0] for c in pos[:2]) + ". 다만 " + ", ".join(c[0] for c in neg[:1])
    elif pos or neg:
        txt = ", ".join(c[0] for c in (pos or neg)[:3])
    elif neu:
        txt = ", ".join(c[0] for c in neu[:2])
    else:
        bits = []
        if r.get("r1m") is not None: bits.append(f"1개월 {_p(r['r1m'])}")
        if r.get("pe"): bits.append(f"PER {r['pe']:.0f}배")
        txt = "뚜렷한 변화 없음" + (" · " + " · ".join(bits) if bits else "")
    if (pos or neg) and neu and len(txt) < 40:
        txt += ", " + neu[0][0]
    txt += "."
    nx = r.get("c_next")
    if nx is not None:
        d = pd.Timestamp(nx).date()
        if today <= d <= today + dt.timedelta(days=14):
            txt += f" {d.month}/{d.day} 실적 발표 예정."
    return txt

# ---------------------------------------------------------------- 컨센서스 (저장소 consensus/ 최신 파일)
def consensus_latest():
    """종목별 가장 최근 스냅숏(최근 7일 안) + 전체 이력. 허브 수집분이 없으면 저장소 S&P 500 파일로"""
    from . import consensus as cons
    H = cons.load(400)
    if H.empty:
        files = sorted((ROOT / "consensus").glob("*/*.csv.gz"))
        if not files:
            return pd.DataFrame(), None, H
        d = pd.read_csv(files[-1], dtype={"period": str, "field": str})
        d["ticker"] = d.ticker.str.replace(".", "-", regex=False)
        return d, files[-1].name[:10], H
    last = H.date.max()
    recent = H[H.date >= (pd.Timestamp(last) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")]
    mx = recent.groupby("ticker").date.transform("max")
    return recent[recent.date == mx], last, H


def consensus_hist(H):
    """프로: 종목별 일별 이력 — 내년 EPS 전망, 30일 상향·하향 수, 평균 목표가, 애널리스트 수"""
    if H.empty:
        return {}
    sel = [("eps_trend", "+1y", "current", "eps1y"), ("eps_rev", "+1y", "upLast30days", "up"), ("eps_rev", "+1y", "downLast30days", "dn"),
           ("pt", "now", "mean", "pt"), ("eps", "+1y", "numberOfAnalysts", "n")]
    parts = []
    for b, per, f, name in sel:
        x = H[(H.block == b) & (H.period == per) & (H.field == f)][["date", "ticker", "value"]].rename(columns={"value": name})
        parts.append(x.set_index(["ticker", "date"]))
    W = pd.concat(parts, axis=1).reset_index().sort_values(["ticker", "date"])
    return {t: {"d": g.date.tolist(), **{c: g[c].round(4).tolist() for c in ["eps1y", "up", "dn", "pt", "n"] if c in g}}
            for t, g in W.groupby("ticker")}


def consensus_table(d, asof):
    if d is None or d.empty:
        return pd.DataFrame(), asof
    piv = lambda b, p, f: d[(d.block == b) & (d.period == p) & (d.field == f)].set_index("ticker").value
    up, dn = piv("eps_rev", "+1y", "upLast30days"), piv("eps_rev", "+1y", "downLast30days")
    n = piv("eps", "+1y", "numberOfAnalysts")
    cur, ago90 = piv("eps_trend", "+1y", "current"), piv("eps_trend", "+1y", "90daysAgo")
    ptm, ptc = piv("pt", "now", "mean"), piv("pt", "now", "current")
    rec = d[(d.block == "rec") & (d.period == "0m")].pivot_table(index="ticker", columns="field", values="value")
    buy = (rec.get("strongBuy", 0) + rec.get("buy", 0)) / rec.sum(axis=1)
    eh = d[(d.block == "ehist") & (d.field == "surprisePercent")].sort_values("period")
    last_s = eh.groupby("ticker").value.last()
    beats = eh.groupby("ticker").tail(4).assign(b=lambda x: x.value > 0).groupby("ticker").b.sum()
    C = pd.DataFrame({"c_up": up, "c_dn": dn, "c_n": n, "c_chg90": cur / ago90 - 1, "c_upside": ptm / ptc - 1, "c_buy": buy,
                      "c_eps_g": piv("eps", "+1y", "growth"), "c_rev_g": piv("rev", "+1y", "growth"), "c_eps1y": cur,
                      "c_surp": last_s, "c_beats": beats})
    C["c_ratio"] = (C.c_up - C.c_dn) / np.maximum(C.c_n.fillna(0), (C.c_up + C.c_dn).fillna(0)).replace(0, np.nan)
    C.index = C.index.str.replace(".", "-", regex=False)
    return C, asof


# ---------------------------------------------------------------- 메인
def run(limit=0, **_):
    global OUT
    R = Run("build")
    t0 = dt.datetime.now()
    final = DATA / "site"
    tmp = DATA / "site.new"                       # 다 만든 뒤에만 바꿔 끼움 (중간 실패 시 이전 결과 유지)
    shutil.rmtree(tmp, ignore_errors=True)
    OUT = tmp / "api" / "v1"
    U = uni.load()
    S = U[U.kind == "stock"].copy()
    E = U[U.kind == "etf"].copy()
    if limit:
        S, E = S.head(limit), E.head(max(3, limit // 5))
    P = read(DATA / "profile" / "profile.parquet").set_index("ticker") if (DATA / "profile" / "profile.parquet").exists() else pd.DataFrame()
    log("가격 읽는 중")
    years = sorted((DATA / "prices" / "daily").glob("*.parquet"))
    PX = pd.concat([pd.read_parquet(p) for p in years], ignore_index=True)
    PX = PX[PX.ticker.isin(set(S.ticker) | set(E.ticker))].sort_values(["ticker", "date"])
    ACT = read(DATA / "prices" / "actions.parquet")
    pxg = dict(tuple(PX.groupby("ticker")))
    # 재무
    log("재무 표준화 중")
    FA = read(DATA / "sec" / "facts.parquet")
    FA = FA[FA.cik.isin(set(S.cik.dropna().astype(int)))]
    FA = FA.assign(end_dt=pd.to_datetime(FA.end, errors="coerce"), start_dt=pd.to_datetime(FA.start, errors="coerce"))
    fin, ftab = {}, {}
    for cik, G in FA.groupby("cik"):
        try:
            fc = fin_company(G)
            fin[int(cik)] = fin_metrics(fc)
            ftab[int(cik)] = fin_tables(fc)
        except Exception as e:
            R.warning(f"재무 {cik}: {str(e)[:60]}")
    # 보조 자료
    FL = read(DATA / "sec" / "filings.parquet")
    INS = read(DATA / "sec" / "insider.parquet")
    if not INS.empty:
        INS["date"] = pd.to_datetime(INS["date"], errors="coerce")
        INS["value"] = INS.shares * INS.price
    SV = pd.concat([read(p) for p in sorted((DATA / "short" / "volume").glob("*.parquet"))[-2:]], ignore_index=True) if list((DATA / "short" / "volume").glob("*.parquet")) else pd.DataFrame()
    SI = read(DATA / "profile" / "short_interest.parquet")
    OP = pd.concat([read(p) for p in sorted((DATA / "options").glob("*.parquet"))], ignore_index=True) if list((DATA / "options").glob("*.parquet")) else pd.DataFrame()
    NW = pd.concat([read(p) for p in sorted((DATA / "news").glob("*.parquet"))[-2:]], ignore_index=True) if list((DATA / "news").glob("*.parquet")) else pd.DataFrame()
    EH = read(sorted((DATA / "etf" / "holdings").glob("*.parquet"))[-1]) if list((DATA / "etf" / "holdings").glob("*.parquet")) else pd.DataFrame()
    EF = read(DATA / "etf" / "funds.parquet")
    F13 = read(DATA / "f13" / "holdings.parquet")
    MG = read(DATA / "f13" / "managers.parquet")
    TK = read(DATA / "sec" / "tenk_features.parquet")
    TS = read(DATA / "sec" / "tenk_newsents.parquet")
    c_snap, c_asof, c_H = consensus_latest()
    C, c_asof = consensus_table(c_snap, c_asof)
    c_hist = consensus_hist(c_H)
    now = pd.Timestamp.now().normalize()
    if not FL.empty:
        FL = FL[FL.cik.isin(set(S.cik.dropna().astype(int)))]
        FL = FL.assign(filed=pd.to_datetime(FL.filed, errors="coerce"))
    E0 = pd.DataFrame()
    grp = lambda df, k: dict(tuple(df.groupby(k))) if not df.empty else {}
    FLg, INSg, SVg, OPg, NWg, TKg, ACTg = grp(FL, "cik"), grp(INS, "ticker"), grp(SV, "ticker"), grp(OP, "ticker"), grp(NW, "ticker"), grp(TK, "ticker"), grp(ACT, "ticker")
    TSg = grp(TS, "ticker")

    # ETF 편입 역조회
    etf_in = {}
    if not EH.empty:
        eh = EH[EH.holding.notna()].copy()
        eh["holding"] = eh.holding.astype(str).str.replace(".", "-", regex=False).str.replace(" ", "-", regex=False)
        for t, g in eh.groupby("holding"):
            etf_in[t] = g.sort_values("weight", ascending=False)[["etf", "weight"]].head(15).values.tolist()
    # 13F
    g13 = {}
    if not F13.empty:
        F13 = F13[F13.put_call.isna() & F13.ticker.notna()]
        periods = sorted(F13.period.unique())
        last_p = periods[-1]
        prev_p = periods[-2] if len(periods) > 1 else None
        ko = dict(zip(MG.manager_cik, MG.manager_ko)) if not MG.empty else {}
        cur13 = F13[F13.period == last_p].groupby(["ticker", "manager_cik"]).agg(v=("value_usd", "sum"), sh=("shares", "sum")).reset_index()
        prv13 = F13[F13.period == prev_p].groupby(["ticker", "manager_cik"]).shares.sum() if prev_p is not None else pd.Series(dtype=float)
        for t, g in cur13.groupby("ticker"):
            rows = []
            for r in g.sort_values("v", ascending=False).itertuples():
                ps = prv13.get((t, r.manager_cik)) if len(prv13) else None
                rows.append({"m": ko.get(r.manager_cik, str(r.manager_cik)), "v": r.v, "sh": r.sh,
                             "chg": None if ps is None else (r.sh / ps - 1 if ps else None), "new": ps is None and prev_p is not None})
            new_n = sum(1 for x in rows if x["new"]) + sum(1 for x in rows if (x["chg"] or 0) > 0.05)
            sold = 0
            if prev_p is not None:
                prev_m = set(F13[(F13.period == prev_p) & (F13.ticker == t)].manager_cik)
                sold = len(prev_m - set(g.manager_cik))
            g13[t] = {"period": last_p, "holders": rows, "net": new_n - sold - sum(1 for x in rows if (x["chg"] or 0) < -0.05)}

    log("종목별 지표 계산·저장 중")
    rows, n_files = [], 0
    for r in S.itertuples():
        t = r.ticker
        p = P.loc[t] if t in P.index else pd.Series(dtype=object)
        g = pxg.get(t)
        tc = tech(g) if g is not None else {}
        cik = int(r.cik) if r.cik == r.cik else None
        fm = fin.get(cik, {}) if cik else {}
        mcap = nz(float(p.get("marketCap"))) if p.get("marketCap") == p.get("marketCap") and p.get("marketCap") is not None else None
        if mcap is None and tc.get("px") and fm.get("_shares"):
            mcap = tc["px"] * fm["_shares"]
        usd = fm.get("cur", "USD") == "USD"
        row = {"t": t, "n": p.get("shortName") if isinstance(p.get("shortName"), str) else r.name, "k": "stock",
               "sec": p.get("sector"), "ind": p.get("industry"), "mcap": mcap,
               "idx": ",".join(x for x, f in (("S&P500", "in_sp500"), ("NDX", "in_ndx"), ("DOW", "in_dji"), ("R1000", "in_r1000")) if getattr(r, f, False)),
               **{k: v for k, v in tc.items() if k != "asof"}, **{k: v for k, v in fm.items() if not k.startswith("_")}}
        if usd and mcap:
            row.update(pe=div(mcap, fm.get("ni")) if (fm.get("ni") or 0) > 0 else None, ps=div(mcap, fm.get("rev")),
                       pb=div(mcap, fm.get("_equity")) if (fm.get("_equity") or 0) > 0 else None, fcfy=div(fm.get("fcf"), mcap),
                       shy=div((fm.get("_buyback") or 0) + (fm.get("_divpaid") or 0), mcap))
        # 배당수익률: 최근 12개월 배당 / 종가
        if tc.get("px"):
            ac = ACTg.get(t, E0)
            dv = ac[ac.date >= now - pd.Timedelta(days=365)].dividend.sum() if len(ac) else 0
            row["dy"] = dv / tc["px"] if dv else 0.0
        # 컨센서스
        if t in C.index:
            c = C.loc[t]
            row.update({k: c[k] for k in ["c_up", "c_dn", "c_n", "c_ratio", "c_chg90", "c_upside", "c_buy", "c_eps_g", "c_rev_g", "c_surp", "c_beats"]})
            if c.get("c_eps1y") and c["c_eps1y"] > 0 and tc.get("px"):
                row["c_fpe"] = tc["px"] / c["c_eps1y"]
        ts_ = p.get("earningsTimestampStart") if p.get("earningsTimestampStart") == p.get("earningsTimestampStart") else p.get("earningsTimestamp")
        if ts_ is not None and ts_ == ts_:
            try:
                ed = pd.to_datetime(float(ts_), unit="s").date()
                row["c_next"] = ed if ed >= (now - pd.Timedelta(days=3)).date() else None
            except Exception:
                pass
        # 공매도·옵션
        sv = SVg.get(t)
        if sv is not None:
            sv = sv.sort_values("date")
            if len(sv) >= 20:
                rr = (sv.short_vol / sv.total_vol)
                row["sv"] = rr.tail(20).mean()
                row["sv_chg"] = rr.tail(20).mean() - rr.iloc[-40:-20].mean() if len(sv) >= 40 else None
        if not SI.empty:
            si = SI[SI.ticker == t].sort_values("date")
            if len(si):
                row["si"] = si.shortPercentOfFloat.iloc[-1]
        op = OPg.get(t)
        if op is not None:
            op = op.sort_values("date")
            if len(op):
                o = op.iloc[-1]
                row.update(iv=o["iv_atm30"], pcr=o["pc_vol"], skew=o["skew"])
        # 공시·내부자
        fl = FLg.get(cik, FL.iloc[0:0])
        k8 = fl[fl.form.str.startswith("8-K") & (fl.filed >= now - pd.Timedelta(days=30))]
        row["k8"] = len(k8)
        if len(fl[fl.form.str.startswith("8-K")]):
            l8 = fl[fl.form.str.startswith("8-K")].sort_values("filed").iloc[-1]
            labs = [ITEMS_8K.get(x.strip()) for x in str(l8["items"]).split(",") if ITEMS_8K.get(x.strip())]
            row["k8_last"] = f"{l8.filed:%m-%d} " + (", ".join(labs) if labs else "8-K")
        k10 = fl[fl.form.isin(["10-K", "20-F", "40-F"])]
        row["k10"] = k10.filed.max() if len(k10) else None
        row["f144"] = int(((fl.form == "144") & (fl.filed >= now - pd.Timedelta(days=30))).sum())
        row["g13d"] = int((fl.form.str.contains("13D|13G", regex=True) & (fl.filed >= now - pd.Timedelta(days=90))).sum())
        ins = INSg.get(t, INS.iloc[0:0])
        if len(ins):
            i90 = ins[ins.date >= now - pd.Timedelta(days=90)]
            b, sl = i90[i90.code == "P"], i90[i90.code == "S"]
            row.update(ib=b.value.sum(), is_=sl.value.sum(), ibn=b.owner.nunique(), ib_last=ins[ins.code == "P"].date.max() if (ins.code == "P").any() else None)
            row["is"] = row.pop("is_")
        tk = TKg.get(t, TK.iloc[0:0]).sort_values("filed") if t in TKg else TK.iloc[0:0]
        if len(tk):
            last = tk.iloc[-1]
            row.update(rf_new=last.get("rf_new"), rf_sim=last.get("sim_rf"), md_unc=last.get("md_unc"))
        # 뉴스·ETF·13F
        nw = NWg.get(t, NW.iloc[0:0]).sort_values("published") if t in NWg else NW.iloc[0:0]
        if len(nw):
            row["nw7"] = int((nw.published >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).sum())
            row["nw_last"] = nw.title.iloc[-1][:90]
        row["etfn"] = len(etf_in.get(t, []))
        if t in g13:
            row["g13"], row["g13_chg"] = len(g13[t]["holders"]), g13[t]["net"]
        row["s1"] = summary_line(row, now.date())
        rows.append(row)

        # ---- 종목 상세 (free / pro)
        detail = {"t": t, "n": row["n"], "summary": (p.get("longBusinessSummary") or "")[:1200] if isinstance(p.get("longBusinessSummary"), str) else "",
                  "web": p.get("website") if isinstance(p.get("website"), str) else None, "emp": p.get("fullTimeEmployees"),
                  "m": row, "asof": tc.get("asof")}
        if g is not None and len(g):
            g2 = g[g.date >= g.date.max() - pd.Timedelta(days=730)]
            detail["px"] = {"d": g2.date.dt.strftime("%Y-%m-%d").tolist(), "o": g2.open.round(2).tolist(), "h": g2.high.round(2).tolist(),
                            "l": g2.low.round(2).tolist(), "c": g2.close.round(2).tolist(), "v": g2.volume.astype(int).tolist()}
            wk = g.set_index("date").adj_close.resample("W-FRI").last().dropna()
            detail["wk"] = {"d": wk.index.strftime("%Y-%m-%d").tolist(), "c": wk.round(2).tolist()}
        if cik in ftab:
            an, qt = ftab[cik]
            detail["fin"] = {"annual": an[-5:], "quarterly": qt, "cur": fm.get("cur")}
        detail["filings"] = [{"d": x.filed, "f": x.form, "items": ", ".join(ITEMS_8K.get(i.strip(), "") for i in str(x["items"]).split(",") if ITEMS_8K.get(i.strip())),
                              "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{str(x.accession).replace('-', '')}/{x.doc}"}
                             for _, x in fl.sort_values("filed", ascending=False).head(40).iterrows() if x.form not in ("4", "4/A", "3", "5")] if len(fl) else []
        if len(ins):
            detail["insider"] = [{"d": x.date, "who": x.owner, "title": x.title or ("이사" if x.is_director else "10% 주주" if x.is_10pct else ""),
                                  "code": x.code, "sh": x.shares, "px": x.price, "v": x.value, "plan": bool(x.plan_10b5_1)}
                                 for x in ins.sort_values("date", ascending=False).head(40).itertuples()]
        if sv is not None and len(sv):
            sv = sv.tail(120)
            detail["short"] = {"d": sv.date.dt.strftime("%Y-%m-%d").tolist(), "r": (sv.short_vol / sv.total_vol).round(4).tolist()}
        if op is not None and len(op):
            op = op.tail(250)
            if len(op):
                detail["opt"] = {"d": op.date.dt.strftime("%Y-%m-%d").tolist(), "iv": op.iv_atm30.round(4).tolist(), "pcr": op.pc_vol.round(3).tolist()}
        if len(nw):
            detail["news"] = [{"d": x.published, "t": x.title, "s": x.source, "u": x.url, "k": x.kind} for x in nw.sort_values("published", ascending=False).head(25).itertuples()]
        detail["etf_in"] = etf_in.get(t, [])
        if t in g13:
            detail["g13"] = g13[t]
        if len(tk):                                       # 10-K 변화 숫자는 무료 (최근 6건)
            cols = [c for c in ["filed", "form", "prev_filed", "rf_new", "sim_rf", "sim_md", "sim_full", "md_unc", "md_neg", "n_rf"] if c in tk]
            detail["tenk"] = tk.tail(6)[cols].to_dict("records")
        dump(OUT / "free" / "stock" / f"{t}.json", detail)
        pro = {"t": t}
        if t in c_hist:
            pro["cons_hist"] = c_hist[t]
        if cik in ftab:
            pro["fin_annual_full"] = ftab[cik][0]
        if t in TSg:                                      # 새 위험 문장 원문은 프로 — 가장 최근 10-K 것만
            ts = TSg[t]
            ts = ts[ts.filed == ts.filed.max()].sort_values("rank").head(40)
            pro["tenk_new"] = {"filed": ts.filed.iloc[0], "prev_acc": ts.prev_acc.iloc[0] if "prev_acc" in ts else None,
                               "sentences": ts.sentence.tolist()}
        dump(OUT / "pro" / "stock" / f"{t}.json", pro)
        n_files += 2

    # ---- ETF
    log("ETF 저장 중")
    efi = EF.set_index("etf") if not EF.empty else pd.DataFrame()
    for r in E.itertuples():
        t = r.ticker
        p = P.loc[t] if t in P.index else pd.Series(dtype=object)
        g = pxg.get(t)
        tc = tech(g) if g is not None else {}
        exp = p.get("netExpenseRatio") if p.get("netExpenseRatio") == p.get("netExpenseRatio") else p.get("annualReportExpenseRatio")
        exp = exp / 100 if isinstance(exp, (int, float)) and exp == exp else None   # yfinance는 % 단위
        dv = ACT[(ACT.ticker == t) & (ACT.date >= now - pd.Timedelta(days=365))].dividend.sum() if not ACT.empty else 0
        row = {"t": t, "n": p.get("longName") if isinstance(p.get("longName"), str) else t, "k": "etf", "grp": getattr(r, "etf_group", None),
               "fam": p.get("fundFamily"), "cat": p.get("category"), "aum": p.get("totalAssets"), "exp": exp,
               "dy": (dv / tc["px"]) if tc.get("px") and dv else 0.0, **{k: v for k, v in tc.items() if k != "asof"}}
        if not OP.empty:
            op = OP[OP.ticker == t].sort_values("date")
            if len(op):
                row.update(iv=op.iv_atm30.iloc[-1], pcr=op.pc_vol.iloc[-1])
        row["s1"] = summary_line(row, now.date())
        rows.append(row)
        h = EH[EH.etf == t].sort_values("weight", ascending=False) if not EH.empty else EH
        info = efi.loc[t].to_dict() if t in efi.index else {}
        detail = {"t": t, "m": row, "summary": (p.get("longBusinessSummary") or "")[:1200] if isinstance(p.get("longBusinessSummary"), str) else "",
                  "holdings": h.head(60)[["holding", "name", "weight"]].values.tolist() if len(h) else [], "n_holdings": len(h),
                  "hold_src": h.source.iloc[0] if len(h) else None,
                  "sectors": json.loads(info["sectors"]) if isinstance(info.get("sectors"), str) else None,
                  "assets": json.loads(info["assets"]) if isinstance(info.get("assets"), str) else None}
        if g is not None and len(g):
            g2 = g[g.date >= g.date.max() - pd.Timedelta(days=730)]
            detail["px"] = {"d": g2.date.dt.strftime("%Y-%m-%d").tolist(), "c": g2.close.round(2).tolist(), "v": g2.volume.astype(int).tolist()}
            wk = g.set_index("date").adj_close.resample("W-FRI").last().dropna()
            detail["wk"] = {"d": wk.index.strftime("%Y-%m-%d").tolist(), "c": wk.round(2).tolist()}
        if not ACT.empty:
            dd = ACT[(ACT.ticker == t) & (ACT.dividend > 0)].sort_values("date").tail(40)
            detail["div"] = [[x.date, x.dividend] for x in dd.itertuples()]
        dump(OUT / "free" / "etf" / f"{t}.json", detail)
        n_files += 1

    # ---- 국내 상장 미국 ETF
    KD = pd.concat([read(p) for p in sorted((DATA / "kr_etf" / "daily").glob("*.parquet"))], ignore_index=True) if list((DATA / "kr_etf" / "daily").glob("*.parquet")) else pd.DataFrame()
    if not KD.empty:
        KD = KD.sort_values(["code", "date"])
        US_MAP = [("PHLX", "SOXX"), ("필라델피아", "SOXX"), ("Dividend 100", "SCHD"), ("배당다우", "SCHD"), ("NASDAQ 100", "QQQ"),
                  ("NASDAQ-100", "QQQ"), ("나스닥100", "QQQ"), ("S&P 500", "VOO"), ("S&P500", "VOO")]
        from .kr_etf import US_KEYS
        krows = []
        for code, g in KD.groupby("code"):
            nm = str(g["name"].iloc[-1]) if "name" in g else ""
            if not US_KEYS.search(nm) and not US_KEYS.search(str(g.index_name.iloc[-1]) if "index_name" in g else ""):
                continue
            g = g.dropna(subset=["close"])
            if len(g) < 5:
                continue
            last = g.iloc[-1]
            name = str(last.get("name"))
            iname = str(last.get("index_name", ""))
            us = next((u for k, u in US_MAP if k in iname), None) or next((u for k, u in US_MAP if k in name), None)
            if us and re.search(r"레버리지|인버스|커버드|채권|2X|합성", name):
                us = None
            c = g.close.values
            k = {"code": code, "n": name, "idx": iname, "us": us, "px": last.close, "nav": last.get("nav"), "dev": last.get("deviation"),
                 "aum": last.get("net_assets"), "val": g.value.tail(20).mean() if "value" in g else None,
                 "r1m": c[-1] / c[-22] - 1 if len(c) > 22 else None, "r1y": c[-1] / c[-253] - 1 if len(c) > 253 else None,
                 "hedged": "(H)" in name}
            krows.append(k)
            g2 = g[g.date >= g.date.max() - pd.Timedelta(days=730)]
            dump(OUT / "free" / "kr_etf" / f"{code}.json", {"code": code, "n": name, "m": k, "d": g2.date.dt.strftime("%Y-%m-%d").tolist(),
                                                             "c": g2.close.tolist(), "nav": g2.nav.tolist() if "nav" in g2 else None,
                                                             "dev": g2.deviation.round(3).tolist() if "deviation" in g2 else None})
        dump(OUT / "free" / "kr_etf.json", {"asof": KD.date.max(), "rows": krows})

    # ---- universe.json + market.json + meta.json
    U2 = pd.DataFrame(rows)
    fields = {k: {"label": v[0], "cat": v[1], "fmt": v[2], "tier": v[3]} for k, v in FIELDS.items()}
    keys = [k for k in FIELDS if k in U2.columns] + ["grp", "fam", "cat", "aum", "exp", "c_next"]
    keys = list(dict.fromkeys(keys))
    pro_keys = [k for k, v in FIELDS.items() if v[3] == "pro"]
    free_rows = U2[[k for k in keys if k in U2.columns and k not in pro_keys]].to_dict("records")
    dump(OUT / "free" / "universe.json", {"asof": PX.date.max(), "consensus_asof": c_asof, "fields": fields, "cats": CATS, "rows": free_rows})
    dump(OUT / "pro" / "universe_pro.json", {"rows": U2[["t"] + [k for k in pro_keys if k in U2.columns]].to_dict("records")})
    st = U2[U2.k == "stock"]
    sec = st.groupby("sec").agg(n=("t", "size"), r1d=("r1d", "median"), r1m=("r1m", "median"), r1y=("r1y", "median"),
                                pe=("pe", "median"), rev_g=("rev_g", "median"), a200=("d200", lambda s: (s > 0).mean()),
                                c_ratio=("c_ratio", "median")).reset_index().to_dict("records")
    idx = {t: {k: U2.set_index("t").loc[t].get(k) for k in ["px", "r1d", "r1m", "rytd", "r1y"]} for t in ["SPY", "QQQ", "DIA", "IWM"] if t in set(U2.t)}
    mk = {"asof": PX.date.max(), "breadth_200": (st.d200 > 0).mean(), "breadth_50": (st.d50 > 0).mean(),
          "adv": int((st.r1d > 0).sum()), "dec": int((st.r1d < 0).sum()), "sectors": sec, "indices": idx,
          "new_hi": int((st.hi52 >= -0.001).sum()), "new_lo": int((st.lo52 <= 0.001).sum())}
    vix = ROOT / "data" / "VIX.csv"
    if vix.exists():
        v = pd.read_csv(vix).dropna()
        mk["vix"] = float(v.iloc[-1, 4])
    fx = ROOT / "data" / "KRW_X.csv"                 # 원/달러 (원화 기준 수익률용, 최근 2년)
    if fx.exists():
        f = pd.read_csv(fx, usecols=["Date", "Close"]).dropna()
        f = f[f.Date >= str((pd.Timestamp.now() - pd.Timedelta(days=740)).date())]
        mk["krw"] = {"d": f.Date.tolist(), "c": f.Close.round(2).tolist()}
    dump(OUT / "free" / "market.json", mk)
    stat = {s["source"]: {k: s.get(k) for k in ("ok", "finished_utc", "seconds", "rows_new", "n_warnings")} for s in load_status()}
    dump(OUT / "meta.json", {"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "price_asof": PX.date.max(),
                                           "stocks": len(S), "etfs": len(E), "kr_etfs": len(krows) if not KD.empty else 0,
                                           "sources": stat})
    size = sum(f.stat().st_size for f in OUT.rglob("*.json")) / 1e6
    cov = {k: f"{U2[U2.k == 'stock'][k].notna().mean()*100:.0f}%" for k in ["rev", "pe", "r1y", "c_ratio", "sv", "iv", "ib", "rf_new", "nw7", "g13"] if k in U2}
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    OUT = final / "api" / "v1"
    R.set(stocks=len(S), etfs=len(E), files=n_files, size_mb=round(size, 1), coverage=", ".join(f"{k} {v}" for k, v in cov.items()),
          seconds_build=(dt.datetime.now() - t0).seconds, rows_new=len(U2))
    return R.done()
