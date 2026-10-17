#!/usr/bin/env python3
"""
나스닥 과매도 → NQ 선물 매수 전략: 매일 신호 판단 · 모의 기록 · 텔레그램 알림 · 현황 대시보드
(검증 규칙 = strategy2/combo_core.py, 2000~2026 64회 거래와 동일하게 재현)

규칙
  신호: VIX 종가 >= 25 이고
        (a) 나스닥 종합(IXIC) 음봉 (종가/시가−1) <= −2 × 60일 수익률 표준편차(전일까지)   [직전 신호 후 5거래일 이상]
     또는 (b) 과매도 점수 P1 이 2 이상으로 올라선 날  [점수 0 으로 돌아와야 재무장, 5거래일 간격]
        P1 = (a)의 음봉 여부 + RSI14·켈트너·스토캐스틱·MACD 가 각각 극단(1988~ 홀수 해 하위 2%) 인 개수
  진입: 신호일 다음 NQ 세션 시가 (한국시간 다음 날 아침 07:00/08:00 재개장)
  청산: IXIC 종가 > 5일 이동평균인 날, 또는 신호 후 5거래일째 → 다음 NQ 세션 시가
  비중: min(1, 25 / VIX)   포지션은 하나만
사용: python strategy/nq_signal.py   (저장소 루트에서, data/ 폴더 필요)
환경변수(선택): TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PAGES_URL
"""
import json, os, sys, datetime, html
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data")
ST = os.path.join(ROOT, "strategy")
DOCS = os.path.join(ROOT, "docs")
GO_LIVE = "2026-10-19"            # 이 날 이후 신호부터 '실전 검증' 기록
VIX_MIN = 25.0
THR = {  # 1988~2026 홀수 해 하위 2% (검증 시 고정값)
    "RSI14": 31.92714541304668,
    "KELT": -2.513919282645016,
    "STOCH": 0.010889137795328678,
    "MACD": -0.683611557056227,
}
LABEL = {"C2": "2σ 음봉", "RSI14": "RSI(14)", "KELT": "켈트너 (종가−EMA20)/ATR", "STOCH": "스토캐스틱 %K(14)", "MACD": "MACD 히스토그램/σ"}


# ───────────────────────── 계산 ─────────────────────────
def load(name):
    d = pd.read_csv(os.path.join(DATA, f"{name}.csv"), parse_dates=["Date"]).set_index("Date").sort_index()
    d.index = pd.DatetimeIndex(d.index.date)
    return d[~d.index.duplicated(keep="last")]


def clean_ix(d):
    d = d[(d.Open > 0) & (d.Close > 0) & (d.High > 0) & (d.Low > 0)]
    bad = (d.Open == d.Close).astype(float).rolling(60, min_periods=60).mean()
    d = d.loc[(bad < 0.05).idxmax():]
    return d[~((d.Open == d.Close) & (d.High == d.Low))]


def rsi(c, n):
    x = c.diff()
    up = x.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-x.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def compute():
    ix = clean_ix(load("IXIC"))
    ix = ix[ix.index >= "1988-01-01"].copy()
    vix = load("VIX").Close.reindex(ix.index)
    nq = load("NQ_F"); nq = nq[(nq.Open > 0) & (nq.Low > 0)]
    c, h, l, o = ix.Close, ix.High, ix.Low, ix.Open
    sig = c.pct_change().rolling(60, min_periods=50).std()
    F = pd.DataFrame(index=ix.index)
    F["vix"] = vix
    F["candle"] = c / o - 1
    F["z"] = F.candle / sig.shift(1)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    F["RSI14"] = rsi(c, 14)
    F["KELT"] = (c - c.ewm(span=20).mean()) / tr.rolling(14).mean()
    F["STOCH"] = (c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min())
    F["MACD"] = (c.ewm(span=12).mean() - c.ewm(span=26).mean()).pipe(lambda m: m - m.ewm(span=9).mean()) / (c * sig)
    F["C2"] = (F.z <= -2).astype(int)
    for k in THR:
        F[f"x_{k}"] = (F[k] <= THR[k]).astype(int)
    F["P1"] = F.C2 + sum(F[f"x_{k}"] for k in THR)
    F["sma5"] = c.rolling(5).mean()
    F["close"] = c
    vhi = (F.vix >= VIX_MIN).values
    # (a) 2σ 음봉 + VIX
    a, last = set(), -99
    for i in np.where(F.C2.values.astype(bool) & vhi)[0]:
        if i - last >= 5:
            a.add(i); last = i
    F.attrs["last_a"] = last
    # (b) 점수 2 이상으로 올라섬 (VIX 무관하게 무장 상태 추적, 신호는 VIX 충족 시만)
    b, armed, last = set(), True, -99
    arm = np.zeros(len(F), bool)
    for i, s in enumerate(F.P1.values):
        if not armed and s == 0:
            armed = True
        arm[i] = armed
        if armed and s >= 2 and i - last >= 5:
            armed = False; last = i
            if vhi[i]:
                b.add(i)
    F["armed"] = arm
    F.attrs["armed_next"], F.attrs["last_b"] = armed, last
    sigs = sorted(a | b)
    return ix, F, nq, sigs, a, b


def ind_last(d):
    """마지막 행의 RSI14·켈트너·스토캐스틱·MACD (compute 와 같은 식)"""
    c, h, l = d.Close, d.High, d.Low
    sig = c.pct_change().rolling(60, min_periods=50).std()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return dict(RSI14=rsi(c, 14).iloc[-1], KELT=((c - c.ewm(span=20).mean()) / tr.rolling(14).mean()).iloc[-1],
                STOCH=((c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min())).iloc[-1],
                MACD=((c.ewm(span=12).mean() - c.ewm(span=26).mean()).pipe(lambda m: m - m.ewm(span=9).mean()) / (c * sig)).iloc[-1])


def levels(ix, F):
    """다음 세션 나스닥 종가가 얼마 이하로 끝나면 각 조건을 충족하는지 (가상의 다음 봉: 시가=전일 종가)"""
    base = ix.iloc[-600:][["Open", "High", "Low", "Close"]]
    p0 = float(base.Close.iloc[-1])
    nxt = base.index[-1] + pd.Timedelta(days=1)
    def val(k, c):
        d = pd.concat([base, pd.DataFrame(dict(Open=[p0], High=[max(p0, c)], Low=[min(p0, c)], Close=[c]), index=[nxt])])
        return ind_last(d)[k]
    out = {}
    for k in THR:
        lo, hi = p0 * 0.70, p0 * 1.03
        if val(k, lo) > THR[k]:
            out[k] = None; continue                          # −30% 로도 안 됨
        if val(k, hi) <= THR[k]:
            out[k] = hi; continue                            # 이미 충족 수준
        for _ in range(30):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if val(k, m) <= THR[k] else (lo, m)
        out[k] = lo
    sig_next = float(ix.Close.pct_change().iloc[-60:].std())
    lv = sorted([v for v in out.values() if v is not None], reverse=True)
    return dict(p0=p0, lv=out, candle_pct=-2 * sig_next, p1_level=lv[1] if len(lv) >= 2 else None,
                armed=bool(F.attrs.get("armed_next", True)))


def replay(ix, F, nq, sigs, a, b):
    """모든 신호를 규칙대로 재생 → 거래 목록 (마지막 거래는 진행 중일 수 있음)"""
    out, busy = [], pd.Timestamp("1900-01-01")
    n = len(ix)
    for i in sigs:
        dt = ix.index[i]
        if dt < nq.index[0]:
            continue
        ek = nq.index.searchsorted(dt, "right")
        if ek < len(nq) and nq.index[ek] <= busy:
            continue
        if ek >= len(nq) and busy == pd.Timestamp.max:
            continue
        why = []
        if i in a:
            why.append(f"2σ 음봉 (캔들 {100*F.candle.iloc[i]:.1f}% = {F.z.iloc[i]:.1f}σ)")
        if i in b:
            parts = [LABEL[k] for k in ["C2"] + list(THR) if F[k if k == "C2" else f"x_{k}"].iloc[i]]
            why.append(f"과매도 점수 {int(F.P1.iloc[i])} ({', '.join(parts)})")
        w = float(min(1.0, VIX_MIN / F.vix.iloc[i]))
        t = dict(signal_date=dt.date().isoformat(), vix=round(float(F.vix.iloc[i]), 2), weight=round(w, 3), why=" + ".join(why),
                 live=dt >= pd.Timestamp(GO_LIVE))
        j = next((jj for jj in range(i + 1, min(i + 6, n)) if F.close.iloc[jj] > F.sma5.iloc[jj]), None)
        if j is None and i + 5 < n:
            j = i + 5
        if ek < len(nq):
            t.update(entry_date=nq.index[ek].date().isoformat(), entry=float(nq.Open.iloc[ek]))
        if j is None:                                   # 아직 청산 조건 없음 → 보유 중
            t.update(status="보유" if ek < len(nq) else "진입 예정", held=n - 1 - i)
            out.append(t); busy = pd.Timestamp.max; break
        t.update(exit_signal_date=ix.index[j].date().isoformat(),
                 exit_why="종가 > 5일선" if F.close.iloc[j] > F.sma5.iloc[j] else "5거래일 만료", held=j - i)
        xk = nq.index.searchsorted(ix.index[j], "right")
        if xk >= len(nq) or ek >= len(nq):
            t.update(status="청산 예정")
            out.append(t); busy = pd.Timestamp.max; break
        t.update(exit_date=nq.index[xk].date().isoformat(), exit=float(nq.Open.iloc[xk]), status="완료")
        t["ret"] = t["exit"] / t["entry"] - 1
        t["pnl"] = t["ret"] * w
        out.append(t); busy = nq.index[xk]
    return out


def today_status(ix, F, nq, trades):
    T = len(F) - 1; r = F.iloc[T]; d = F.index[T].date().isoformat()
    last = trades[-1] if trades else None
    cond = [
        ("VIX", f"{r.vix:.1f}", f"≥ {VIX_MIN:.0f}", bool(r.vix >= VIX_MIN)),
        ("2σ 음봉", f"캔들 {100*r.candle:+.2f}% = {r.z:+.2f}σ", "≤ −2σ", bool(r.C2)),
        ("RSI(14)", f"{r.RSI14:.1f}", f"≤ {THR['RSI14']:.1f}", bool(r.x_RSI14)),
        ("켈트너 (종가−EMA20)/ATR", f"{r.KELT:+.2f}", f"≤ {THR['KELT']:.2f}", bool(r.x_KELT)),
        ("스토캐스틱 %K(14)", f"{100*r.STOCH:.1f}%", f"≤ {100*THR['STOCH']:.1f}%", bool(r.x_STOCH)),
        ("MACD 히스토그램/σ", f"{r.MACD:+.2f}", f"≤ {THR['MACD']:.2f}", bool(r.x_MACD)),
        ("과매도 점수 P1", f"{int(r.P1)} (무장 {'O' if F.armed.iloc[T] else 'X — 점수 0 복귀 대기'})", "≥ 2 로 올라섬", bool(r.P1 >= 2)),
    ]
    st = dict(date=d, ixic=float(r.close), sma5=float(r.sma5), cond=cond, nq_last=float(nq.Close.iloc[-1]),
              nq_date=nq.index[-1].date().isoformat())
    if last and last["status"] != "완료":
        st["mode"] = last["status"]; st["trade"] = last
        if last["status"] == "진입 예정":
            st["headline"] = f"매수 신호 — 다음 NQ 세션 시가 진입 (비중 {100*last['weight']:.0f}%)"
        elif last["status"] == "보유":
            pl = st["nq_last"] / last["entry"] - 1
            st["headline"] = f"보유 중 {last['held']}일째 / 5일 — 평가 {100*pl:+.2f}% (NQ {st['nq_last']:,.0f})"
            st["exit_check"] = f"IXIC 종가 {r.close:,.0f} vs 5일선 {r.sma5:,.0f} → {'넘음' if r.close > r.sma5 else '아래'}"
        else:
            st["headline"] = f"청산 신호 ({last['exit_why']}) — 다음 NQ 세션 시가 청산"
    else:
        st["mode"] = "대기"
        if r.vix < VIX_MIN:
            st["headline"] = f"대기 — VIX {r.vix:.1f} < 25 (공포 구간 아님)"
        else:
            st["headline"] = f"대기 — VIX {r.vix:.1f} 공포 구간, 과매도 조건 미충족 (점수 {int(r.P1)})"
    return st


# ───────────────────────── 대시보드 ─────────────────────────
def near_text(L, html_mode=False):
    """근접 현황 문구 (대시보드·텔레그램 공용)"""
    p0 = L["p0"]
    f = lambda v: "−30% 넘게 하락해도 미충족" if v is None else (f"{v:,.0f} 이하 ({100*(v/p0-1):+.1f}%)" if v < p0 else "현재 이미 충족 수준")
    rows = [("2σ 음봉", f"시가 대비 {100*L['candle_pct']:.2f}% 이하로 마감")] + \
           [(LABEL[k], f(L["lv"][k])) for k in THR]
    if L["p1_level"] is None:
        head = "과매도 점수 경로: 지표 2개를 동시에 충족하기 어려움"
    elif not L["armed"]:
        head = "과매도 점수 경로: 무장 해제 상태 (점수 0으로 돌아온 뒤 다시 가능) — 2σ 음봉 경로만 유효"
    else:
        head = f"과매도 점수 2 도달: 나스닥 종가 {L['p1_level']:,.0f} 이하 ({100*(L['p1_level']/p0-1):+.1f}%)"
    return head, rows


def dashboard(ix, F, trades, st, a, b):
    os.makedirs(DOCS, exist_ok=True)
    k0 = max(0, len(F) - 756)
    G = F.iloc[k0:]
    X = ix.iloc[k0:]
    ds = [x.isoformat() for x in G.index.date]
    num = lambda s: [None if v != v else round(float(v), 4) for v in s]
    ent = [t for t in trades if t["signal_date"] >= ds[0]]
    sig_i = [i for i in sorted(a | b) if i >= k0]
    payload = dict(
        d=ds, o=num(X.Open), h=num(X.High), l=num(X.Low), c=num(X.Close), sma5=num(G.sma5), vix=num(G.vix), z=num(G.z), p1=num(G.P1),
        rsi=num(G.RSI14), kelt=num(G.KELT), stoch=num(100 * G.STOCH), macd=num(G.MACD), thr=THR,
        sig=[dict(d=F.index[i].date().isoformat(), y=float(F.close.iloc[i]), skip=not any(t["signal_date"] == F.index[i].date().isoformat() for t in trades)) for i in sig_i],
        ex=[dict(d=t["exit_signal_date"], y=float(F.close.loc[pd.Timestamp(t["exit_signal_date"])])) for t in ent if t.get("exit_signal_date")],
    )
    done = [t for t in trades if t["status"] == "완료"]
    bt = [t for t in done if not t["live"]]; lv = [t for t in done if t["live"]]
    def summ(L):
        if not L:
            return "—"
        p = np.array([t["pnl"] for t in L])
        return f"{len(L)}회 · 승률 {100*(p>0).mean():.0f}% · 평균 {100*p.mean():+.2f}% · 누적 {100*(np.prod(1+p)-1):+.1f}%"
    rows, old = [], []
    for k, t in enumerate(reversed(trades)):
        tgt = rows if (t["live"] or k < 8) else old
        tgt.append("<tr class='{}'><td>{}</td><td>{}</td><td>{:.1f}</td><td>{:.0f}%</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            "live" if t["live"] else "", t["signal_date"], t["why"], t["vix"], 100 * t["weight"],
            f"{t.get('entry_date','')} {t['entry']:,.0f}" if "entry" in t else "—",
            f"{t.get('exit_date','')} {t['exit']:,.0f}" if "exit" in t else "—", t.get("exit_why", ""),
            f"{100*t['ret']:+.2f}%" if "ret" in t else t["status"], f"{100*t['pnl']:+.2f}%" if "pnl" in t else ""))
    cond_rows = "".join(f"<tr><td>{n}</td><td>{v}</td><td>{th}</td><td class='{'ok' if ok else 'no'}'>{'충족' if ok else '—'}</td></tr>" for n, v, th, ok in st["cond"])
    extra = ""
    if st.get("trade"):
        t = st["trade"]
        extra = f"<p class='sub'>신호일 {t['signal_date']} · {t['why']} · VIX {t['vix']} · 비중 {100*t['weight']:.0f}%" + \
                (f" · 진입 {t['entry_date']} {t['entry']:,.0f}" if "entry" in t else "") + "</p>"
        if st.get("exit_check"):
            extra += f"<p class='sub'>청산 확인: {st['exit_check']}</p>"
    near = ""
    if st.get("near"):
        hd, rr = near_text(st["near"])
        near = (f"<div class='card'><b>다음 세션 근접 현황</b> <span class='sub'>(전일 종가 {st['near']['p0']:,.0f} 기준, 가상의 다음 봉으로 계산한 근사치 · VIX ≥ 25 유지 필요)</span>"
                f"<p class='hl'>{hd}</p><table><tr><th>조건</th><th>나스닥이 이렇게 끝나면 충족</th></tr>" +
                "".join(f"<tr><td>{a_}</td><td>{b_}</td></tr>" for a_, b_ in rr) + "</table></div>")
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__NEAR__", near) \
        .replace("__HEAD__", st["headline"]).replace("__DATE__", st["date"]).replace("__MODE__", st["mode"]) \
        .replace("__EXTRA__", extra).replace("__COND__", cond_rows).replace("__ROWS__", "".join(rows)).replace("__OLD__", "".join(old)) \
        .replace("__BT__", summ(bt)).replace("__LV__", summ(lv)).replace("__GEN__", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")) \
        .replace("__GOLIVE__", GO_LIVE)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(html)


TEMPLATE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NQ 과매도 전략</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script src="charts.js"></script>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e1dc;--card:#fff;--ok:#1a7f4b;--no:#9a9a94;--acc:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#9b9a94;--line:#2c2c2a;--card:#1d1d1b;--ok:#4ade80;--no:#6b6b66;--acc:#fb923c}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:980px;margin:auto;padding:16px}
h1{font-size:18px;margin:0 0 4px} .sub{color:var(--mut);font-size:13px;margin:2px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}
.head{font-size:20px;font-weight:650;margin:6px 0} .mode{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--acc);color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:13px} td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:500} .ok{color:var(--ok);font-weight:650} .hl{font-weight:650;color:var(--acc);margin:6px 0} .no{color:var(--no)} tr.live td{background:rgba(194,65,12,.08)}
.scroll{overflow-x:auto} .scroll table{min-width:820px} .scroll td{white-space:nowrap} .scroll td:nth-child(2){white-space:normal;min-width:220px} .chart{width:100%}
</style></head><body><main>
<nav style="margin-bottom:6px"><a href="index.html" style="color:var(--acc);margin-right:14px;font-size:14px;text-decoration:none;font-weight:700">나스닥 → NQ</a><a href="kospi.html" style="color:var(--acc);font-size:14px;text-decoration:none">코스피 반등</a></nav>
<h1>나스닥 과매도 → NQ 매수</h1>
<p class="sub">기준일 __DATE__ (나스닥 종가) · 생성 __GEN__ · 실전 검증 시작 __GOLIVE__</p>
<div class="card"><span class="mode">__MODE__</span><div class="head">__HEAD__</div>__EXTRA__
<p class="sub">진입 = VIX ≥ 25 그리고 (2σ 음봉 또는 과매도 점수가 2 이상으로 올라섬) · 청산 = 나스닥 종가 &gt; 5일선 또는 5거래일</p></div>
__NEAR__<div class="card"><b>오늘의 판단 근거</b><div><table><tr><th>조건</th><th>오늘 값</th><th>기준</th><th></th></tr>__COND__</table></div></div>
<div class="card"><b>지표 차트</b> <span class="sub">(▲ 매수 신호 · ▼ 청산 신호 · 회색 ▲ 보유 중이라 건너뛴 신호 · 점선 = 기준선 · 손가락으로 좌우 이동·확대)</span><div id="ch" class="chart"></div></div>
<div class="card"><b>거래 기록</b><p class="sub">백테스트(2000~): __BT__<br>실전 검증: __LV__</p>
<div class="scroll"><table><tr><th>신호일</th><th>근거</th><th>VIX</th><th>비중</th><th>진입(NQ 시가)</th><th>청산</th><th>청산 사유</th><th>수익</th><th>비중 반영</th></tr>__ROWS__</table></div>
<details><summary class="sub">이전 백테스트 거래 전체 보기</summary><div class="scroll"><table>__OLD__</table></div></details></div>
<p class="sub" style="text-align:right">차트: <a href="https://www.tradingview.com/" style="color:inherit">TradingView Lightweight Charts</a></p>
</main><script>
const D=__DATA__;const K=window.CHART_COLORS;
const mk=[...D.sig.filter(x=>!x.skip).map(x=>({time:x.d,position:'belowBar',color:K.acc,shape:'arrowUp',text:'매수'})),
 ...D.sig.filter(x=>x.skip).map(x=>({time:x.d,position:'belowBar',color:K.gray,shape:'arrowUp',text:''})),
 ...D.ex.map(x=>({time:x.d,position:'aboveBar',color:K.blue,shape:'arrowDown',text:'청산'}))];
const gray=v=>K.gray;
buildStack(document.getElementById('ch'),{dates:D.d,defaultRange:'1Y',panes:[
 {title:'나스닥 종합',height:330,series:[{type:'candle',o:D.o,h:D.h,l:D.l,c:D.c,up:K.green,down:K.red,digits:0},{type:'line',v:D.sma5,color:K.blue,width:1,name:'5일선',digits:0,lastValue:false}],markers:mk},
 {title:'VIX',height:110,series:[{type:'line',v:D.vix,color:K.fg,digits:1}],lines:[{value:25,label:'25'}]},
 {title:'캔들/σ',height:100,series:[{type:'hist',v:D.z,colorFn:v=>v<=-2?K.acc:K.gray,digits:2}],lines:[{value:-2,label:'−2σ'}]},
 {title:'과매도 점수',height:90,series:[{type:'hist',v:D.p1,colorFn:v=>v>=2?K.acc:K.gray,digits:0}],lines:[{value:2,label:'2'}]},
 {title:'RSI(14)',height:95,series:[{type:'line',v:D.rsi,color:K.fg,digits:1}],lines:[{value:D.thr.RSI14,label:''}]},
 {title:'켈트너',height:95,series:[{type:'line',v:D.kelt,color:K.fg,digits:2}],lines:[{value:D.thr.KELT,label:''}]},
 {title:'스토캐스틱 %K',height:95,series:[{type:'line',v:D.stoch,color:K.fg,digits:1}],lines:[{value:100*D.thr.STOCH,label:''}]},
 {title:'MACD/σ',height:120,series:[{type:'line',v:D.macd,color:K.fg,digits:2}],lines:[{value:D.thr.MACD,label:''}]}]});
</script></body></html>"""


# ───────────────────────── 알림 ─────────────────────────
def chart_png(ix, F, trades, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("NanumGothic", "Noto Sans CJK KR", "AppleGothic"):
        if any(f in x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f; break
    plt.rcParams["axes.unicode_minus"] = False
    G = F.iloc[-130:]; X = ix.loc[G.index]
    fig, axs = plt.subplots(3, 1, figsize=(8, 7), sharex=True, gridspec_kw=dict(height_ratios=[3, 1.3, 1.3]))
    axs[0].plot(X.index, X.Close, color="#1d1d1b", lw=1.2, label="나스닥 종합")
    axs[0].plot(G.index, G.sma5, color="#2563eb", lw=0.9, label="5일선")
    for t in trades:
        sd = pd.Timestamp(t["signal_date"])
        if sd >= G.index[0]:
            axs[0].scatter([sd], [F.close.loc[sd] * 0.98], marker="^", s=80, color="#c2410c", zorder=5)
        if t.get("exit_signal_date") and pd.Timestamp(t["exit_signal_date"]) >= G.index[0]:
            ed = pd.Timestamp(t["exit_signal_date"])
            axs[0].scatter([ed], [F.close.loc[ed] * 1.02], marker="v", s=70, color="#2563eb", zorder=5)
    axs[0].legend(loc="upper left", fontsize=8); axs[0].set_title(f"기준일 {G.index[-1].date()}", fontsize=10)
    axs[1].plot(G.index, G.vix, color="#1d1d1b", lw=1); axs[1].axhline(25, ls=":", color="#c2410c"); axs[1].set_ylabel("VIX")
    axs[2].bar(G.index, G.P1, color=["#c2410c" if v >= 2 else "#9a9a94" for v in G.P1]); axs[2].axhline(2, ls=":", color="#c2410c")
    axs[2].set_ylabel("과매도 점수")
    for a_ in axs:
        a_.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def telegram(text, photo=None):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[텔레그램 미설정]\n" + text); return False
    import requests
    base = f"https://api.telegram.org/bot{tok}"
    if photo:
        with open(photo, "rb") as f:
            r = requests.post(f"{base}/sendPhoto", data=dict(chat_id=chat, caption=text[:1024], parse_mode="HTML"), files=dict(photo=f), timeout=30)
    else:
        r = requests.post(f"{base}/sendMessage", data=dict(chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True), timeout=30)
    print("텔레그램", r.status_code, r.text[:200])
    if r.status_code != 200:                          # 실행 요약에 경고 표시 (데이터 커밋은 계속)
        print(f"::error title=텔레그램 전송 실패::{r.status_code} {r.text[:150]}")
    return r.status_code == 200


def main():
    ix, F, nq, sigs, a, b = compute()
    trades = replay(ix, F, nq, sigs, a, b)
    st = today_status(ix, F, nq, trades)
    if st["mode"] == "대기":
        st["near"] = levels(ix, F)
    os.makedirs(ST, exist_ok=True)
    pd.DataFrame(trades).to_csv(os.path.join(ST, "nq_trades.csv"), index=False, encoding="utf-8-sig")
    dashboard(ix, F, trades, st, a, b)
    # 알림: 진입 신호 · 청산 신호 · 근접 현황(VIX ≥ 25 이고 대기 중일 때 매일). 같은 일은 한 번만
    sp = os.path.join(ST, "nq_state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else {"sent": []}
    url = os.environ.get("PAGES_URL", "")
    link = f"\n<a href=\"{url}\">현황 대시보드</a>" if url else ""
    ev = None
    last = trades[-1] if trades else None
    T = F.index[-1].date().isoformat()
    E = html.escape                                   # 텔레그램 HTML 모드: <, >, & 는 반드시 변환
    cond = E("\n".join(f"{'✅' if ok else '▫️'} {n}: {v} ({th})" for n, v, th, ok in st["cond"]))
    if last and last["signal_date"] == T and last["status"] in ("진입 예정", "보유"):
        ev = (f"entry:{T}", f"🟠 <b>NQ 매수 신호</b> ({T} 나스닥 종가 기준)\n근거: {E(last['why'])}\nVIX {last['vix']} → 비중 {100*last['weight']:.0f}%\n"
                            f"실행: 다음 NQ 세션 시가 매수 (재개장 한국시간 07:00/08:00)\n청산: 나스닥 종가 &gt; 5일선 또는 5거래일\n\n{cond}")
    elif last and last.get("exit_signal_date") == T:
        ev = (f"exit:{T}", f"🔵 <b>NQ 청산 신호</b> ({T})\n사유: {E(last['exit_why'])} (보유 {last['held']}거래일)\n"
                           f"진입 {last.get('entry_date','')} {last.get('entry', float('nan')):,.0f} → 현재 NQ {st['nq_last']:,.0f}\n실행: 다음 NQ 세션 시가 청산")
    elif st["mode"] == "대기" and F.vix.iloc[-1] >= VIX_MIN:
        hd, rr = near_text(st["near"])
        first = " — 공포 구간 진입" if F.vix.iloc[-2] < VIX_MIN else ""
        ev = (f"near:{T}", f"⚪️ <b>NQ 근접 현황</b> ({T} 종가 기준, VIX {F.vix.iloc[-1]:.1f}{first})\n"
                           f"오늘 밤 나스닥 마감 기준, VIX 25 이상 유지 시:\n<b>{E(hd)}</b>\n" +
                           "\n".join(f"▫️ {E(a_)}: {E(b_)}" for a_, b_ in rr) +
                           f"\n(현재 점수 {int(F.P1.iloc[-1])}, 전일 종가 {st['near']['p0']:,.0f}, 근사치)")
    if ev and ev[0] not in S["sent"]:
        png = os.path.join(ST, "nq_chart.png") if not ev[0].startswith("near") else None
        try:
            if png:
                chart_png(ix, F, trades, png)
        except Exception as e:
            print("차트 실패", e); png = None
        if telegram(ev[1] + link, png) is not False:      # 실패하면 다음 실행에서 다시 시도
            S["sent"] = (S["sent"] + [ev[0]])[-200:]
    S.update(last_run=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), basis_date=T, mode=st["mode"], headline=st["headline"])
    json.dump(S, open(sp, "w"), ensure_ascii=False, indent=1)
    if os.environ.get("TELEGRAM_TEST"):
        png = os.path.join(ST, "nq_chart.png"); chart_png(ix, F, trades, png)
        telegram(f"🧪 연결 테스트 — {E(st['headline'])}\n\n{cond}{link}", png)
    print(st["headline"])


if __name__ == "__main__":
    main()
