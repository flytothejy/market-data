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
BAL = {"assets": ["Assets"], "liab": ["Liabilities"], "equity": ["StockholdersEquity", "Equity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
       "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], "ltd": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesPayable"],
       "ca": ["AssetsCurrent"], "cl": ["LiabilitiesCurrent"], "shares": ["EntityCommonStockSharesOutstanding"]}


ANNUAL_FORMS = ("10-K", "20-F", "40-F")


def _latest(df):
    """같은 기간 값이 여러 번 보고되면: 1년짜리 기간은 연간 보고서 값을 우선, 그다음 최근 제출분
    (회사가 10-Q에 1년 기간을 잘못 붙여 낸 사례가 있었음: FIX 2025년 매출이 1분기 값으로 덮임)"""
    d = df.assign(_days=(df.end_dt - df.start_dt).dt.days)
    d["_pref"] = ((d._days >= 350) & d.form.astype(str).str.startswith(ANNUAL_FORMS)).astype(int)
    return d.sort_values(["_pref", "filed"]).drop_duplicates(["start", "end"], keep="last").drop(columns=["_days", "_pref"])


def flow_series(df, outlier=False, deduped=False):
    """흐름 항목 → (분기별 dict end→값, 연간 dict end→값). 누적(3·6·9·12개월) 값에서 분기를 역산
    직접 보고된 3개월 값이 역산값과 크게 다르면 역산값을 씀 (LHX: 3개월 기간에 연간 값이 붙어 있던 사례)"""
    if df is None or df.empty:
        return {}, {}
    d = df.dropna(subset=["start_dt"])
    if len(d):
        # 연간 보고서에서 3개월 기간에 1년 값이 붙은 경우 (LHX) → 같은 해 9개월 누적의 시작일로 고쳐 1년 기간으로
        # (fp는 '문서'의 기간이라 10-K 안의 4분기 3개월 값도 FY로 표시됨 → fp가 아니라 값의 크기로 판단)
        dd0 = (d.end_dt - d.start_dt).dt.days
        q3m = d[(dd0 >= 80) & (dd0 <= 100)]
        med = float(q3m.val.abs().median()) if len(q3m) >= 4 else 0
        bad = d.form.astype(str).str.startswith(ANNUAL_FORMS) & (dd0 >= 80) & (dd0 <= 100) & (med > 0) & (d.val.abs() > 2.5 * med)
        if bad.any():
            deduped = False
            d = d.copy()
            dd = (d.end_dt - d.start_dt).dt.days
            for i in d.index[bad]:
                e = d.at[i, "end_dt"]
                nine = d[(dd >= 255) & (dd <= 290) & ((e - d.end_dt).dt.days.between(80, 100))]   # 같은 회계연도의 9개월 누적
                d.at[i, "start_dt"] = nine.start_dt.iloc[0] if len(nine) else e - pd.Timedelta(days=364)
            d.loc[bad, "start"] = d.loc[bad, "start_dt"].dt.strftime("%Y-%m-%d")
    d = d if deduped else _latest(d)
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
    derived, direct = {}, {}
    by_start = {}
    for i in np.where(okq)[0]:
        by_start.setdefault(st[i], {})[k_arr[i]] = i
    for cum in by_start.values():
        for k in range(2, 5):
            if k in cum and (k - 1) in cum:
                derived[E[cum[k]]] = vals[cum[k]] - vals[cum[k - 1]]
    for i in np.where((days >= 80) & (days <= 100))[0]:
        direct[E[i]] = vals[i]
    q = dict(derived)
    for e, v in direct.items():
        dv = derived.get(e)
        if dv is None or dv == 0 or 0.67 <= abs(v / dv) <= 1.5:
            q[e] = v
    out = {}
    for e in sorted(q):
        if out and (e - max(out)).days < 10:
            out.pop(max(out))
        out[e] = q[e]
    # 앞뒤 분기보다 2.5배 넘게 튀는 분기는 잘못 붙은 값으로 보고 뺌 (연간 값이 분기 기간에 붙은 경우)
    ks = sorted(out)
    if outlier and len(ks) >= 5:
        bad = []
        for i, e in enumerate(ks):
            nb = [abs(out[ks[j]]) for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(ks)]
            med = float(np.median(nb)) if nb else 0
            if med > 0 and abs(out[e]) > 2.5 * med and all(abs(out[e]) > 2.5 * x for x in nb[:2] + nb[2:] if x):
                bad.append(e)
        for e in bad:
            out.pop(e)
    return out, annual


def ttm(qs, back=0):
    ks = sorted(qs)
    if len(ks) < 4 + back:
        return None
    sel = ks[len(ks) - 4 - back: len(ks) - back]
    span = (sel[-1] - sel[0]).days
    return sum(qs[k] for k in sel) if 250 <= span <= 300 else None


def pick(G, tags, unit_pref=("USD", "USD/shares", "shares")):
    """후보 태그 중 가장 최근 값이 있는 태그·단위 (G: 태그→DataFrame dict) — 잔액 항목용"""
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


def combine(G, tags, unit_pref=("USD", "USD/shares", "shares"), component_ratio=1.5):
    """흐름 항목: 기간마다 우선순위 높은 태그 값을 쓰되, 여러 태그를 이어 붙임
    (회사가 해마다·분기마다 태그를 바꿔 쓰는 경우가 많음: ADP는 연간만 Revenues, 분기는 계약매출 태그)
    0은 무시, 더 낮은 순위 태그가 1.5배 이상 크면 앞의 값을 부분 항목으로 보고 큰 값을 씀 (FLS·CPT)"""
    parts = [G[t].assign(_rank=r) for r, t in enumerate(tags) if t in G and len(G[t])]
    if not parts:
        return EMPTY
    d = pd.concat(parts, ignore_index=True)
    d = d[d.start_dt.notna() & (d.val != 0)]
    if d.empty:
        return EMPTY
    units = d.unit.value_counts().index.tolist()
    u = next((x for x in unit_pref if x in units), units[0])
    d = d[d.unit == u]
    days = (d.end_dt - d.start_dt).dt.days
    d = d.assign(_pref=((days >= 350) & d.form.astype(str).str.startswith(ANNUAL_FORMS)).astype(int))
    d = d.sort_values(["_pref", "filed"]).drop_duplicates(["_rank", "start", "end"], keep="last")   # 태그별 최신 값
    d = d.sort_values(["start", "end", "_rank"])
    first = d.drop_duplicates(["start", "end"], keep="first")
    if component_ratio < 1e6:
        mx = d.sort_values(["start", "end", "val"]).drop_duplicates(["start", "end"], keep="last")
        m = first.merge(mx[["start", "end", "val"]].rename(columns={"val": "_mx"}), on=["start", "end"])
        swap = m._mx > m.val.abs() * component_ratio
        if swap.any():
            keys = set(zip(m.start[swap], m.end[swap]))
            first = pd.concat([first[~pd.Series(list(zip(first.start, first.end)), index=first.index).isin(keys)],
                               mx[pd.Series(list(zip(mx.start, mx.end)), index=mx.index).isin(keys)]])
    return first.drop(columns=["_rank", "_pref"])


EMPTY = pd.DataFrame(columns=["tag", "unit", "start", "end", "val", "filed", "form", "accn", "end_dt", "start_dt"])
REV_FALLBACK = ["RevenueFromContractWithCustomerIncludingAssessedTax"]


def fin_company(G0):
    G = dict(tuple(G0.groupby("tag")))
    gmax = G0.end_dt.max()
    res = {"q": {}, "a": {}}
    main = [t for t in REV if t not in REV_FALLBACK] + ["OperatingLeaseLeaseIncome", "RealEstateRevenueNet", "LeaseIncome"] + REV_FALLBACK
    rv = combine(G, main)            # 세금 포함 매출은 맨 뒤 순위 (TJX처럼 그 태그만 쓰는 회사 대비)
    cur = (rv.unit.iloc[0] if len(rv) else "USD")
    qs, an = flow_series(rv, outlier=True)
    # 은행: 이자 순수익 + 비이자 수익 (또는 '이자비용 차감 후 매출')이 최근 값으로 있으면 그것을 매출로
    nii, nonii, rnet = combine(G, CONCEPTS["nii"]), combine(G, CONCEPTS["nonii"]), combine(G, ["RevenuesNetOfInterestExpense"])
    recent = lambda x: len(x) and x.end_dt.max() >= gmax - pd.Timedelta(days=200)
    if recent(rnet):
        qs, an = flow_series(rnet)
    elif recent(nii) and recent(nonii):
        q1, a1 = flow_series(nii)
        q2, a2 = flow_series(nonii)
        qs = {k: q1[k] + q2[k] for k in q1 if k in q2}
        an = {k: a1[k] + a2[k] for k in a1 if k in a2}
    qs = {k: v for k, v in qs.items() if v > 0}           # 음수·0 매출 분기는 잘못된 역산으로 보고 버림
    if qs and max(qs) < gmax - pd.Timedelta(days=200):     # 매출 태그가 몇 년째 끊긴 회사 → 옛 값을 지금 값처럼 보이지 않게
        qs = {}
    res["q"]["rev"], res["a"]["rev"] = qs, an
    for c, tags in CONCEPTS.items():
        if c in ("nii", "nonii"):
            continue
        res["q"][c], res["a"][c] = flow_series(combine(G, tags, component_ratio=1e9))   # 우선순위만 (큰 값 규칙 없음)
        if res["q"][c] and max(res["q"][c]) < gmax - pd.Timedelta(days=200):   # 몇 년 전에 끊긴 태그(예: 2013년 매출총이익) → 버림
            res["q"][c], res["a"][c] = {}, {}
    if not res["q"]["gp"] and res["q"]["cogs"]:
        res["q"]["gp"] = {k: res["q"]["rev"][k] - v for k, v in res["q"]["cogs"].items() if k in res["q"]["rev"]}
        res["a"]["gp"] = {k: res["a"]["rev"][k] - v for k, v in res["a"]["cogs"].items() if k in res["a"]["rev"]}
    bal = {}
    for c, tags in BAL.items():
        g = pick(G, tags)
        g = g[g.start_dt.isna()] if len(g) else g
        if len(g) and g.end_dt.max() < gmax - pd.Timedelta(days=200):   # 몇 년 전에 끊긴 잔액(예: 스팩 시절 자본 500만 달러) → 버림
            g = g.iloc[:0]
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
    # 자본이 0 이하이거나 자산의 2% 미만(자사주 매입으로 자본이 거의 없는 회사, 상장 직전 껍데기 자본)이면 PBR·ROE·부채비율은 의미가 없어 비움
    eq = B.get("equity")
    eq = eq if eq is not None and eq >= 1e6 and (not B.get("assets") or eq >= 0.02 * B["assets"]) else None
    P = {c: ttm(Q[c], back=4) for c in Q}
    rq = Q["rev"]
    ks = sorted(rq)
    k4 = ks[-4:] if len(ks) >= 4 else []

    def A(c):   # 이익률은 매출과 같은 4개 분기로 맞춰 계산 (분기가 어긋난 값끼리 나누지 않게)
        q = Q.get(c) or {}
        return sum(q[k] for k in k4) if k4 and all(k in q for k in k4) else None
    rev_qg = None
    if len(ks) >= 5:
        last = ks[-1]
        prev = [k for k in ks if 350 <= (last - k).days <= 380]
        if prev:
            rev_qg = div(rq[last], rq[prev[-1]]) - 1 if div(rq[last], rq[prev[-1]]) else None
    m = {"rev": T["rev"], "rev_g": (div(T["rev"], P["rev"]) - 1) if div(T["rev"], P["rev"]) else None, "rev_qg": rev_qg,
         "gm": div(A("gp"), A("rev")), "om": div(A("opi"), A("rev")), "nm": div(A("ni"), A("rev")), "ni": T["ni"],
         "ni_g": (div(T["ni"], P["ni"]) - 1) if (P["ni"] or 0) > 0 and div(T["ni"], P["ni"]) else None, "eps": T["eps"],
         "fcf": (T["cfo"] - T["capex"]) if T["cfo"] is not None and T["capex"] is not None else T["cfo"],
         "roe": div(T["ni"], eq), "roa": div(T["ni"], B.get("assets")),
         "de": div(B.get("ltd"), eq), "cr": div(B.get("ca"), B.get("cl")),
         "rnd": div(T["rnd"], T["rev"]), "fq": max(ks) if ks else None, "cur": fc["cur"],
         "_buyback": T["buyback"], "_divpaid": T["divpaid"], "_equity": eq, "_shares": B.get("shares")}
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


# ---------------------------------------------------------------- 어긋남 지도 경로
SPANS = {"3m": (14, 7, "r1m"), "1y": (30, 13, "r3m"), "3y": (91, 13, "r6m")}   # 트레일 길이: (점 간격 일, 점 수, 함께 쓰는 가로축)
XMAX = {"r1w": 0.12, "r1m": 0.3, "r3m": 0.5, "r6m": 0.7}                       # 화면 matrix.js XW와 같음
LENS_MAX = {"eps": 0.3, "rev": 0.3, "guru": 5, "short": 0.08, "insider": 1}     # 화면 LENS.max와 같음 (insider는 이미 -1~1)


def ins_y(n):
    """내부자 순매수 금액 → 지도 세로값 (로그 눈금, 화면 LENS.insider.y와 같음)"""
    return float(np.sign(n) * max(0.05, min(1, (math.log10(abs(n)) - 4) / 4.5))) if n else 0.0


def trails(t, g, ET, sv, gh, rq, ih, now):
    """종목을 눌렀을 때 지도 위에 그릴 경로 — 키 '렌즈@길이' (예: rev@1y), 점마다 지도와 같은 기준으로 계산
    점: [날짜, 1주·1개월·3개월·6개월 수익률(그 날짜 기준), 신호 값]
    길이: 3m = 2주 간격 7점, 1y = 1개월 간격 13점, 3y = 분기 간격 13점 (자료가 모자라면 있는 만큼)
    eps    : 3m만 — 야후가 주는 90·60·30·7일 전 전망 (우리 스냅샷이 쌓이면 늘릴 수 있음)
    short  : 공매도 비중 60일 평균 − 직전 60일 평균, 줄면 + (20일은 월 단위로 보면 오락가락이 심해 60일로)
    insider: 그 날짜까지 제출된 최근 90일 임원·이사 장내 순매수 (SEC 과거 자료)
    rev·guru: 분기 자료라 값이 바뀐 분기마다 한 점 (1y·3y)
    화면은 마지막 점을 '현재 점'으로 바꿔 경로의 끝이 지도 위 점과 정확히 겹치게 그림"""
    if g is None or not len(g):
        return {}
    gg = g[["date", "adj_close"]].dropna()
    if gg.empty:
        return {}
    dts, a = gg.date.values, gg.adj_close.values.astype(float)
    last = pd.Timestamp(dts[-1])
    def rets(d):
        i = int(np.searchsorted(dts, np.datetime64(pd.Timestamp(d)), side="right")) - 1
        if i < 0:
            return [None] * 4
        return [round(float(a[i] / a[i - n] - 1), 4) if i - n >= 0 and a[i - n] > 0 else None for n in (5, 21, 63, 126)]
    def pt(d, y):
        return [str(pd.Timestamp(d).date())] + rets(d) + [round(float(y), 4)]
    def grid(span):
        step, n, _ = SPANS[span]
        return [last - pd.Timedelta(days=step * k) for k in range(n - 1, -1, -1)]
    out, full = {}, {}                                   # full: 렌즈별 전체 이력 (재생용 프레임을 만들 때 씀)
    if not ET.empty and t in ET.index:
        e = ET.loc[t]
        base = e.get("90daysAgo")
        if base and base == base and base > 0:
            pts = [pt(last - pd.Timedelta(days=off), float(e.get(f)) / base - 1)
                   for off, f in ((90, "90daysAgo"), (60, "60daysAgo"), (30, "30daysAgo"), (7, "7daysAgo"), (0, "current"))
                   if e.get(f) is not None and e.get(f) == e.get(f)]
            if len(pts) >= 3:
                out["eps@3m"] = pts
                full["eps"] = pts
    if sv is not None and len(sv) >= 130:
        s = sv.sort_values("date")
        m60 = (s.short_vol / s.total_vol).rolling(60, min_periods=45).mean()
        chg = (m60 - m60.shift(60)).values
        sd = s.date.values
        for span in SPANS:
            pts = []
            for d in grid(span):
                i = int(np.searchsorted(sd, np.datetime64(d), side="right")) - 1
                if i >= 0 and chg[i] == chg[i] and (pd.Timestamp(d) - pd.Timestamp(sd[i])).days < 10:
                    pts.append(pt(sd[i], -chg[i]))
            if len(pts) >= 3:
                out[f"short@{span}"] = pts
    if ih is not None and len(ih):
        fd, td, sv_ = ih.filed.values, ih.date.values, np.where(ih.code.values == "P", ih.value.values, -ih.value.values)
        for span in SPANS:
            pts = []
            for d in grid(span):
                d64, lo = np.datetime64(d), np.datetime64(d - pd.Timedelta(days=90))
                m = (fd <= d64) & (td > lo) & (td <= d64)
                pts.append(pt(d, ins_y(float(sv_[m].sum()))))
            if sum(1 for p in pts if p[5]) >= 1 and len(pts) >= 3:      # 기간 안에 거래가 한 번이라도 있어야
                out[f"insider@{span}"] = pts
    if gh and len(gh) >= 3:
        allp = [pt(gh[i][0], gh[i][1] - gh[i - 1][1]) for i in range(1, len(gh))]
        full["guru"] = allp
        for span, days in (("1y", 400), ("3y", 1170)):
            pts = [p for p in allp if pd.Timestamp(p[0]) >= last - pd.Timedelta(days=days)]
            if len(pts) >= 2:
                out[f"guru@{span}"] = pts
    if rq:
        ks = sorted(rq)
        allp = []
        for i in range(7, len(ks)):
            q8 = ks[i - 7:i + 1]
            if (q8[-1] - q8[0]).days > 800:
                continue
            v = [rq[k] for k in q8]
            if all(x and x > 0 for x in v):
                allp.append(pt(q8[-1], (v[7] / v[3] - 1) - (sum(v[4:8]) / sum(v[0:4]) - 1)))
        full["rev"] = allp
        for span, days in (("1y", 400), ("3y", 1170)):
            pts = [p for p in allp if pd.Timestamp(p[0]) >= last - pd.Timedelta(days=days)]
            if len(pts) >= 2:
                out[f"rev@{span}"] = pts
    # 재생용 프레임: 길이별 공통 날짜(격자)마다 [그 길이의 가로축 수익률, 그때 알려진 신호 값]
    fr = {}
    for key in out:
        lens, span = key.split("@")
        xi = {"r1m": 1, "r3m": 2, "r6m": 3}[SPANS[span][2]]
        src = out[key] if lens in ("short", "insider") else full.get(lens, out[key])
        stale = 200 if lens in ("rev", "guru") else 40
        vals = []
        for d in grid(span):
            ds = str(pd.Timestamp(d).date())
            prev = [p for p in src if p[0] <= ds]
            y = prev[-1][5] if prev and (pd.Timestamp(ds) - pd.Timestamp(prev[-1][0])).days <= stale else None
            x = rets(d)[xi]
            vals.append([x, y] if x is not None and y is not None else None)
        fr[key] = ([str(pd.Timestamp(d).date()) for d in grid(span)], vals)
    out["_frames"] = fr
    return out


def trail_pattern(pts, xkey, lens, cur):
    """경로 모양 이름표 — 화면 matrix.js의 patternOf와 같은 규칙
    st 제자리 · zz 오락가락(갔다가 돌아옴) · 그 밖에는 [8방위 방향(↑=신호 개선 →=주가 상승), 꾸준함]
    방향이 있으면 [방향, 꾸준함 0~1] — 화면은 꾸준함 0.7 이상을 '꾸준히'로 표시"""
    xi = {"r1w": 1, "r1m": 2, "r3m": 3, "r6m": 4}[xkey]
    xm, ym = XMAX[xkey], LENS_MAX[lens]
    C = [(max(-1, min(1, p[xi] / xm)), max(-1, min(1, p[5] if lens == "insider" else p[5] / ym))) for p in pts if p[xi] is not None and p[5] is not None]
    if cur is not None:
        if C and pts[-1][0] >= cur[0]:
            C[-1] = cur[1:]
        else:
            C.append(cur[1:])
    if len(C) < 3:
        return None
    X, Y = np.array([c[0] for c in C]), np.array([c[1] for c in C])
    ext = float(np.hypot(X - X[0], Y - Y[0]).max())          # 출발점에서 가장 멀리 간 거리
    if ext < 0.25:
        return "st"
    dx, dy = X[-1] - X[0], Y[-1] - Y[0]
    net = math.hypot(dx, dy)
    if net < 0.4 * ext:
        return "zz"                                             # 멀리 갔다가 출발점 근처로 돌아옴
    # 꾸준함 = 한 걸음씩 볼 때 전체 방향으로 간 거리의 비율 (1 = 한 번도 거꾸로 안 감)
    ux, uy = dx / net, dy / net
    sx_, sy_ = np.diff(X), np.diff(Y)
    path = float(np.hypot(sx_, sy_).sum())
    steady = float(np.maximum(0, sx_ * ux + sy_ * uy).sum()) / path if path else 0
    if net < 0.25:
        return "zz"
    return [["e", "ne", "n", "nw", "w", "sw", "s", "se"][int(((math.degrees(math.atan2(dy, dx)) + 22.5) % 360) // 45)], round(steady, 2)]


# 신호를 평균낼 때 한 종목이 튀어 전체를 끌고 가지 않게 지도 눈금 끝에서 자름 (화면 matrix.js의 max와 같음)
TRAIL_CLIP = {"eps": 0.3, "rev": 0.3, "guru": 5, "short": 0.08, "insider": 1}


def group_trails(items, min_n=3):
    """업종·세부 업종 경로: 같은 순서의 점끼리 시가총액 가중 평균 (점 개수가 다르면 뒤에서부터 맞춤)"""
    def agg(members):
        out = {}
        for key in sorted({k for _, tr in members for k in tr}):
            clip = TRAIL_CLIP.get(key.split("@")[0], 1)
            lens = key
            ms = [(w, tr[lens]) for w, tr in members if tr.get(lens)]
            if len(ms) < min_n:
                continue
            n = int(np.median([len(p) for _, p in ms]))
            pts = []
            for k in range(n, 0, -1):                       # 뒤에서 k번째
                rows = [(w, p[-k]) for w, p in ms if len(p) >= k]
                if len(rows) < min_n:
                    continue
                d = max(set(r[0] for _, r in rows), key=[r[0] for _, r in rows].count)
                vals = []
                for j in range(1, 6):
                    xs = [(w, r[j]) for w, r in rows if r[j] is not None]
                    sw = sum(w for w, _ in xs)
                    v = sum(w * x for w, x in xs) / sw if sw else None
                    if v is not None and j == 5:
                        v = sum(w * max(-clip, min(clip, x)) for w, x in xs) / sw
                    vals.append(round(v, 4) if v is not None else None)
                pts.append([d] + vals)
            if len(pts) >= 2:
                out[lens] = pts
        return out
    res = {"sec": {}, "ind": {}}
    for key, i in (("sec", 0), ("ind", 1)):
        groups = {}
        for it in items:
            k = it[i]
            if isinstance(k, str) and k:                    # 업종 정보가 비어 있으면(NA) 건너뜀
                groups.setdefault(k, []).append((float(it[2]), it[3]))
        for name, members in groups.items():
            if len(members) >= min_n:
                tr = agg(members)
                if tr:
                    res[key][name] = tr
    return res


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
    SUPP = read(DATA / "sec" / "facts_supp.parquet")           # companyfacts에 아직 없는 보고서 (공시 원본에서 보충)
    if not SUPP.empty:
        FA = pd.concat([FA, SUPP[[c for c in FA.columns if c in SUPP.columns]]], ignore_index=True)
    FA = FA[FA.cik.isin(set(S.cik.dropna().astype(int)))]
    FA = FA[["cik", "tag", "unit", "start", "end", "val", "filed", "form", "accn"]]
    FA = FA.assign(end_dt=pd.to_datetime(FA.end, errors="coerce"), start_dt=pd.to_datetime(FA.start, errors="coerce"))
    fin, ftab, revq = {}, {}, {}
    for cik, G in FA.groupby("cik"):
        try:
            fc = fin_company(G)
            revq[int(cik)] = fc["q"].get("rev") or {}
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
    SV = pd.concat([read(p) for p in sorted((DATA / "short" / "volume").glob("*.parquet"))[-4:]], ignore_index=True) if list((DATA / "short" / "volume").glob("*.parquet")) else pd.DataFrame()
    # 내부자 트레일용 긴 이력 (SEC 분기 자료) + 그 뒤 최근분(공시 원문, 임원·이사만)
    IH = read(DATA / "sec" / "insider_hist.parquet")
    if not IH.empty:
        IH = IH[["cik", "filed", "date", "code", "value"]]
    if not INS.empty and "is_officer" in INS:
        c_of = dict(zip(S.ticker, S.cik))
        rec = INS[(INS.is_officer.fillna(False) | INS.is_director.fillna(False)) & INS.code.isin(["P", "S"])].copy()
        rec = rec.assign(cik=rec.ticker.map(c_of), filed=pd.to_datetime(rec.filed, errors="coerce")).dropna(subset=["cik", "filed", "value"])
        if not IH.empty:
            rec = rec[rec.filed > IH.filed.max()]
        IH = pd.concat([IH, rec[["cik", "filed", "date", "code", "value"]].astype({"cik": int})], ignore_index=True) if len(rec) else IH
    IHg = dict(tuple(IH.groupby("cik"))) if not IH.empty else {}
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
    # 13F — 기관마다 가장 최근 분기와 그 직전 분기를 비교 (기관마다 제출 시점이 달라 분기를 하나로 맞추지 않음)
    g13, f13_page, g13_hist = {}, None, {}
    if not F13.empty:
        from .f13 import MANAGERS as F13M
        kind = {c: k for c, _, _, k in F13M}
        ko = {c: n for c, _, n, _ in F13M}
        if not MG.empty:
            ko.update({c: n for c, n in zip(MG.manager_cik, MG.manager_ko) if c not in ko})
        F13 = F13[F13.put_call.isna()].copy()
        F13["period"] = pd.to_datetime(F13.period)
        gmax = F13.period.max()
        tot = F13.groupby(["manager_cik", "period"]).value_usd.sum()           # 티커 매핑 안 된 것까지 포함한 총액 (비중 계산용)
        nm13 = F13.dropna(subset=["ticker"]).groupby("ticker").issuer.first()
        cur_l, prv_l, mlist = [], [], []
        for m, g in F13.groupby("manager_cik"):
            ps = sorted(g.period.unique())
            lp = ps[-1]
            if lp < gmax - pd.Timedelta(days=200):                              # 1년 가까이 13F를 안 낸 곳은 제외
                continue
            pp = ps[-2] if len(ps) > 1 else None
            c = g[g.period == lp].groupby(["ticker"], dropna=False).agg(v=("value_usd", "sum"), sh=("shares", "sum"), issuer=("issuer", "first")).reset_index()
            c["m"] = m; cur_l.append(c)
            if pp is not None:
                q = g[g.period == pp].groupby(["ticker"], dropna=False).agg(v=("value_usd", "sum"), sh=("shares", "sum"), issuer=("issuer", "first")).reset_index()
                q["m"] = m; prv_l.append(q)
            mlist.append((m, lp, pp, g[g.period == lp].filed.max()))
        CUR = pd.concat(cur_l, ignore_index=True) if cur_l else pd.DataFrame()
        PRV = pd.concat(prv_l, ignore_index=True) if prv_l else pd.DataFrame(columns=["ticker", "v", "sh", "issuer", "m"])
        has_prev = {m for m, _, pp, _ in mlist if pp is not None}
        lpd = {m: lp for m, lp, _, _ in mlist}
        prv_sh = PRV.dropna(subset=["ticker"]).set_index(["m", "ticker"]).sh.to_dict()
        prv_v = PRV.dropna(subset=["ticker"]).set_index(["m", "ticker"]).v.to_dict()
        CUR["w"] = [v / tot.get((m, lpd[m]), np.nan) for m, v in zip(CUR.m, CUR.v)]
        CUR["chg"] = [(sh / prv_sh[(m, t)] - 1) if (m, t) in prv_sh and prv_sh[(m, t)] else None for m, t, sh in zip(CUR.m, CUR.ticker, CUR.sh)]
        CUR["new"] = [m in has_prev and (m, t) not in prv_sh for m, t in zip(CUR.m, CUR.ticker)]
        # 종목별
        C1 = CUR.dropna(subset=["ticker"])
        for t, g in C1.groupby("ticker"):
            g = g.assign(k=g.m.map(kind).fillna("guru"), rk=g.m.map(kind).map({"guru": 0, "fund": 1, "inst": 2}).fillna(0))
            rows_ = [{"m": ko.get(r.m, str(r.m)), "k": r.k, "v": r.v, "sh": r.sh, "w": r.w, "chg": r.chg, "new": bool(r.new),
                      "p": str(lpd[r.m].date())} for r in g.sort_values(["rk", "v"], ascending=[True, False]).itertuples()]
            gu = g[g.k == "guru"]
            sold = sum(1 for m in has_prev if kind.get(m, "guru") == "guru" and (m, t) in prv_sh and m not in set(gu.m))
            up = int(gu.new.sum()) + int((gu.chg.fillna(0) > 0.05).sum())
            dn = int((gu.chg.fillna(0) < -0.05).sum()) + sold
            g13[t] = {"period": str(max(lpd[m] for m in g.m).date()), "holders": rows_[:40], "n_guru": len(gu), "net": up - dn, "sold": sold}
        # 투자자 화면용
        mrows = []
        for m, lp, pp, filed in mlist:
            c = CUR[CUR.m == m].sort_values("v", ascending=False)
            label = lambda r: r.ticker if isinstance(r.ticker, str) else None
            top = [{"t": label(r), "n": r.issuer, "w": r.w, "v": r.v, "chg": r.chg, "new": bool(r.new)} for r in c.head(25).itertuples()]
            buys, sells = [], []
            if pp is not None:
                cc = c.dropna(subset=["ticker"]).copy()
                # 가격 변동은 빼고 주식 수 변화분만 금액으로 (이번 분기 말 가격 기준)
                cc["dv"] = [(sh - prv_sh.get((m, t), 0)) * (v / sh if sh else 0) for t, v, sh in zip(cc.ticker, cc.v, cc.sh)]
                buys = [{"t": r.ticker, "n": r.issuer, "dv": r.dv, "new": bool(r.new), "chg": r.chg, "w": r.w}
                        for r in cc[cc.dv > 0].nlargest(10, "dv").itertuples()]
                pv = PRV[(PRV.m == m)].dropna(subset=["ticker"])
                cur_sh = dict(zip(cc.ticker, cc.sh))
                pv = pv.assign(dv=[-(psh - cur_sh.get(t, 0)) * (pvv / psh if psh else 0) for t, psh, pvv in zip(pv.ticker, pv.sh, pv.v)],
                               out=[t not in cur_sh for t in pv.ticker])
                sells = [{"t": r.ticker, "n": r.issuer, "dv": r.dv, "out": bool(r.out)} for r in pv[pv.dv < 0].nsmallest(10, "dv").itertuples()]
            mrows.append({"cik": int(m), "m": ko.get(m, str(m)), "k": kind.get(m, "guru"), "p": str(lp.date()), "filed": str(pd.Timestamp(filed).date()),
                          "prev": str(pd.Timestamp(pp).date()) if pp is not None else None, "total": float(tot.get((m, lp), 0)),
                          "n": int(len(c)), "top10w": float(c.head(10).w.sum()), "top": top, "buys": buys, "sells": sells})
        # 유명 투자자(guru) 합산: 많이 보유·새로 산·판 종목
        G = CUR[CUR.m.map(kind).fillna("guru").eq("guru")].dropna(subset=["ticker"])
        agg = G.groupby("ticker").agg(n=("m", "nunique"), v=("v", "sum"), new=("new", "sum"),
                                      up=("chg", lambda x: int((x.fillna(0) > 0.05).sum()))).reset_index()
        agg["sold"] = agg.ticker.map(lambda t: g13.get(t, {}).get("sold", 0))
        agg["name"] = agg.ticker.map(nm13)
        agg["net"] = agg.ticker.map(lambda t: g13.get(t, {}).get("net", 0))
        # 경로용: 분기마다 이 종목을 가진 유명 투자자 수 (대부분이 제출한 분기만 — 제출 중인 최신 분기는 숫자가 덜 차 있어 제외)
        gk = F13[F13.manager_cik.map(kind).fillna("guru").eq("guru")].dropna(subset=["ticker"])
        mper = gk.groupby("period").manager_cik.nunique()
        gper = sorted(mper[mper >= 0.6 * mper.max()].index)[-5:]
        gcnt = gk[gk.period.isin(gper)].groupby(["ticker", "period"]).manager_cik.nunique()
        for t in gcnt.index.get_level_values(0).unique():
            g13_hist[t] = [(p, int(gcnt.get((t, p), 0))) for p in gper]
        f13_page = {"asof": str(gmax.date()), "managers": sorted(mrows, key=lambda r: ({"guru": 0, "fund": 1, "inst": 2}[r["k"]], -r["total"])),
                    "popular": agg.nlargest(25, ["n", "v"]).to_dict("records"),
                    "bought": agg[(agg.new + agg.up) > 0].assign(b=lambda x: x.new + x.up).nlargest(20, ["b", "v"]).to_dict("records"),
                    "sold": agg.assign(s=agg.sold).query("s > 0").nlargest(20, ["s", "v"]).to_dict("records")}
        # 다 판 종목은 현재 보유(agg)에 없으므로 직전 분기에서 따로 셈
        out_cnt = {}
        for m in has_prev:
            if kind.get(m, "guru") != "guru":
                continue
            cur_t = set(CUR[CUR.m == m].ticker.dropna())
            for t in set(PRV[PRV.m == m].ticker.dropna()) - cur_t:
                out_cnt[t] = out_cnt.get(t, 0) + 1
        if out_cnt:
            so = pd.DataFrame([{"ticker": t, "s": n, "name": nm13.get(t)} for t, n in out_cnt.items()]).nlargest(20, "s")
            f13_page["sold"] = so.to_dict("records")

    import csv as _csv
    KO = {}
    kp = ROOT / "hub" / "ko_names.csv"                  # 한글 회사명 (Wikidata의 SEC CIK 대조 + 직접 보정)
    if kp.exists():
        KO = {r["ticker"]: r["ko"] for r in _csv.DictReader(open(kp, encoding="utf-8"))}
    # 어긋남 지도 경로용: 내년 EPS 전망 추이(현재·7·30·60·90일 전)
    ET = pd.DataFrame()
    if c_snap is not None and not c_snap.empty:
        et = c_snap[(c_snap.block == "eps_trend") & (c_snap.period == "+1y")]
        if len(et):
            ET = et.pivot_table(index="ticker", columns="field", values="value", aggfunc="last")
    log("종목별 지표 계산·저장 중")
    rows, n_files = [], 0
    asof_s = str(PX.date.max().date())                  # 트레일 끝점(지금 점)의 날짜 = 마지막 거래일
    FRAMES = {}                                         # 시간 재생 프레임 {렌즈@길이: {d: 날짜들, t: {종목: [[x, y]|None, ...]}}}
    PAT = {}                                            # 트레일 모양 이름표 {길이: {렌즈: {종목: 코드}}}
    ALL_TR = []                                         # 업종 경로용 (업종, 세부 업종, 시가총액, 종목 경로)
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
                et = pd.to_datetime(float(ts_), unit="s", utc=True).tz_convert("America/New_York")
                ed = et.date()
                if ed >= (now - pd.Timedelta(days=3)).date():
                    row["c_next"] = ed
                    est = p.get("isEarningsDateEstimate")
                    # 시각이 장 전/후로 확정된 경우만 표시 (예상일이면 시각이 의미 없음)
                    if est is not True and est == est:
                        row["c_when"] = "장 전" if et.hour < 12 else "장 후" if et.hour >= 16 else None
                    row["c_est"] = bool(est) if est == est and est is not None else None
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
                row["sv_chg60"] = rr.tail(60).mean() - rr.iloc[-120:-60].mean() if len(sv) >= 120 else None   # 티커맵 공매도 렌즈 (덜 흔들리게 60일)
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
        # 실적 발표 때 주가 반응: 8-K(2.02 실적 발표) 제출일 기준 전날 종가 → 다음날 종가 (장 전·장 후 발표 모두 포함)
        er_hist = []
        if g is not None and len(g) and len(fl):
            e8 = sorted(set(fl[fl.form.str.startswith("8-K") & fl["items"].astype(str).str.contains("2.02", regex=False)].filed.dropna().dt.normalize()))
            # 2.02는 인도량 발표 등에도 쓰임(테슬라) → 분기·연간 보고서 제출일 직전 40일 안의 마지막 2.02만 실적 발표로 봄
            rq = sorted(set(fl[fl.form.isin(["10-Q", "10-K", "20-F", "40-F", "10-Q/A"]) & ~fl.form.str.endswith("/A")].filed.dropna().dt.normalize()))
            ds = []
            for f in rq:
                c = [d for d in e8 if f - pd.Timedelta(days=40) <= d <= f + pd.Timedelta(days=1)]
                if c and (not ds or c[-1] != ds[-1]):
                    ds.append(c[-1])
            if e8 and (not ds or e8[-1] > ds[-1]) and (not rq or e8[-1] > rq[-1]) and (now - e8[-1]).days <= 40:
                ds.append(e8[-1])                         # 방금 발표하고 보고서는 아직 안 낸 경우
            pxa = g.set_index("date").adj_close
            for d in ds[-12:]:
                i = pxa.index.searchsorted(d)
                if 1 <= i and i + 1 < len(pxa):
                    er_hist.append([str(d.date()), round(float(pxa.iloc[i + 1] / pxa.iloc[i - 1] - 1), 4)])
        if er_hist:
            mv = [abs(x[1]) for x in er_hist[-8:]]
            row["er_avg"] = sum(mv) / len(mv)
        er_exp = None
        opx = OPg.get(t)
        if opx is not None and len(opx) and row.get("c_next"):
            o = opx.sort_values("date").iloc[-1]
            try:
                # 발표일 이후 첫 만기(가까운 만기 → 30일 만기 순)의 등가격 내재변동성 → 그 만기까지 예상 변동폭 (±1 표준편차)
                for ek, ik in (("exp_near", "iv_atm_near"), ("exp30", "iv_atm30")):
                    ex = pd.Timestamp(o[ek])
                    dte = (ex - pd.Timestamp(o["date"])).days
                    # 발표 뒤 7일 안에 끝나는 만기만 (멀면 발표와 무관한 평소 변동이 섞여 과거 발표 반응과 비교할 수 없음)
                    if row["c_next"] <= ex.date() <= row["c_next"] + dt.timedelta(days=7) and 0 < dte <= 14 and o[ik] == o[ik]:
                        # 만기까지에는 발표와 무관한 평소 거래일도 섞임 → 평소 변동성(60일)만큼의 분산을 빼서
                        # 과거 발표 반응(전날→다음 날, 2거래일)과 같은 기준으로 맞춤
                        var = float(o[ik]) ** 2 * dte / 365
                        nd = max(0, int(np.busday_count(pd.Timestamp(o["date"]).date() + dt.timedelta(days=1), ex.date() + dt.timedelta(days=1))) - 2)
                        hv = row.get("vol")
                        if hv is not None and hv == hv:
                            var = max(var - hv ** 2 * nd / 252, var * 0.25)
                        row["er_imp"] = math.sqrt(var)
                        er_exp = str(ex.date())
                        break
            except Exception:
                pass
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
            row["g13"], row["g13_chg"] = g13[t]["n_guru"], g13[t]["net"]
        row["s1"] = summary_line(row, now.date())
        if t in KO:
            row["ko"] = KO[t]
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
        detail["trail"] = trails(t, g, ET, SVg.get(t), g13_hist.get(t), revq.get(cik), IHg.get(cik), now)
        for key, (fd, fv) in (detail["trail"].pop("_frames", None) or {}).items():   # 티커맵 시간 재생용 (종목 파일에는 안 넣음)
            F_ = FRAMES.setdefault(key, {}).setdefault(tuple(fd), {})       # 날짜 격자가 같은 종목끼리 (마지막 거래일이 다른 종목은 따로)
            F_[t] = [None if v is None else [round(v[0], 3), round(v[1], 3)] for v in fv]
        # 모양 이름표 (지도 필터용): 지금 점 = 지도 위 점
        ys = {"eps": row.get("c_chg90") if (row.get("c_n") or 0) >= 3 else None,
              "rev": (row["rev_qg"] - row["rev_g"]) if row.get("rev_qg") is not None and row.get("rev_g") is not None else None,
              "guru": row.get("g13_chg"), "short": -row["sv_chg60"] if row.get("sv_chg60") is not None else None,
              "insider": ins_y((row.get("ib") or 0) - (row.get("is") or 0)) if (row.get("ib") or row.get("is")) else None}
        for key, pts in detail["trail"].items():
            lens, span = key.split("@")
            xk = SPANS[span][2]
            if ys.get(lens) is None or row.get(xk) is None:
                continue
            yv = ys[lens] if lens == "insider" else ys[lens] / LENS_MAX[lens]
            code = trail_pattern(pts, xk, lens, (asof_s, max(-1, min(1, row[xk] / XMAX[xk])), max(-1, min(1, yv))))
            if code:
                PAT.setdefault(span, {}).setdefault(lens, {})[t] = code
        if detail["trail"] and row.get("mcap"):
            ALL_TR.append((row.get("sec"), row.get("ind"), row["mcap"], detail["trail"]))
        detail["er"] = {"next": row.get("c_next"), "when": row.get("c_when"), "est": row.get("c_est"), "imp": row.get("er_imp"),
                        "exp": er_exp, "avg": row.get("er_avg"), "hist": er_hist}
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
    keys = [k for k in FIELDS if k in U2.columns] + ["grp", "fam", "cat", "aum", "exp", "c_next", "c_est", "ko"]
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
    dump(OUT / "free" / "sector_trails.json", group_trails(ALL_TR))
    dump(OUT / "free" / "patterns.json", PAT)
    for key, by in FRAMES.items():
        fd, tt = max(by.items(), key=lambda kv: len(kv[1]))     # 가장 많은 종목이 쓰는 격자
        dump(OUT / "free" / "frames" / f"{key}.json", {"d": list(fd), "t": tt})
    if f13_page:
        dump(OUT / "free" / "f13.json", f13_page)
    # 예전 S&P 500 컨센서스 페이지 데이터 (Pages 배포 때 /consensus_data.json 으로 복사)
    try:
        from . import consensus_page
        sp = U2[(U2.k == "stock") & U2.idx.fillna("").str.contains("S&P500", regex=False)] if "idx" in U2 else U2.iloc[0:0]
        cp = consensus_page.build(c_H, dict(zip(U2.t, U2.n)), set(sp.t)) if not c_H.empty and len(sp) else None
        if cp:
            with open(OUT / "free" / "consensus_page.json", "w", encoding="utf-8") as f:
                json.dump(cp, f, ensure_ascii=False, separators=(",", ":"))
            R.set(consensus_page=f"{cp['date']} {cp['n_tickers']}종목 {len(cp['hist'])}일")
    except Exception as e:
        R.warning(f"컨센서스 페이지 데이터 실패: {str(e)[:80]}")
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
