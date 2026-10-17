#!/usr/bin/env python3
"""
코스피 미국발 급락 → 반등 매수 (관찰 알림): 매일 신호 판단 · 모의 기록 · 텔레그램 · 대시보드(docs/kospi.html)
(검증 규칙 = strategy2/multi_index.py 조건 D, 1997~ 지수 19건 +3.81% 승률 95%, KODEX200 8건 +3.73%)

규칙
  신호: 코스피 종합 캔들 (종가/시가−1) <= −2 × 60일 수익률 표준편차(전일까지)
        그리고 그날 아침 끝난 미국장 S&P500 일간 수익률 <= −1%     [직전 신호 후 5거래일 이상]
  진입: 다음 날 시가 (코스피200 선물 08:45 / KODEX200 09:00)
  청산: 코스피 종가 > 5일 이동평균인 날의 다음 날 시가, 최대 10거래일
  포지션은 하나만 (보유 중 신호는 건너뜀)
사용: python strategy/kospi_signal.py   (저장소 루트에서)
"""
import json, os, sys, datetime, html
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nq_signal import telegram, DATA, ST, DOCS  # noqa: E402

GO_LIVE = "2026-10-19"
K, US_DROP, MAXH = 2.0, -0.01, 10


def load(name):
    d = pd.read_csv(os.path.join(DATA, f"{name}.csv"), parse_dates=["Date"]).set_index("Date").sort_index()
    d.index = pd.DatetimeIndex(d.index.date)
    d = d[~d.index.duplicated(keep="last")]
    return d[(d.Open > 0) & (d.Close > 0)]


def compute():
    ks = load("KS11")
    ks = ks[ks.index >= "1997-01-01"].copy()
    spx = load("GSPC").Close.pct_change()
    etf = load("069500_KS")
    F = pd.DataFrame(index=ks.index)
    sig = ks.Close.pct_change().rolling(60, min_periods=50).std().shift(1)
    F["candle"] = ks.Close / ks.Open - 1
    F["sigma"] = sig
    F["z"] = F.candle / sig
    F["us"] = spx.asof(ks.index - pd.Timedelta(days=1)).values      # 그날 아침 끝난 미국 세션
    F["us_date"] = [spx.index[spx.index.searchsorted(d - pd.Timedelta(days=1), "right") - 1].date().isoformat() for d in ks.index]
    F["close"] = ks.Close
    F["sma5"] = ks.Close.rolling(5).mean()
    flag = (F.z <= -K) & (F.us <= US_DROP)
    sigs, last = [], -99
    for i in np.where(flag.values)[0]:
        if i - last >= 5:
            sigs.append(i); last = i
    return ks, F, etf, sigs


def replay(ks, F, etf, sigs):
    out, busy, n = [], -1, len(ks)
    for i in sigs:
        if i <= busy:
            continue
        dt = ks.index[i]
        t = dict(signal_date=dt.date().isoformat(), us_date=F.us_date.iloc[i], us=round(float(F.us.iloc[i]), 4),
                 candle=round(float(F.candle.iloc[i]), 4), z=round(float(F.z.iloc[i]), 2), live=dt >= pd.Timestamp(GO_LIVE))
        if i + 1 < n:
            t.update(entry_date=ks.index[i + 1].date().isoformat(), entry=float(ks.Open.iloc[i + 1]))
            ed = ks.index[i + 1]
            if ed in etf.index:
                t["etf_entry"] = float(etf.Open.loc[ed])
        j = next((jj for jj in range(i + 1, min(i + MAXH + 1, n)) if F.close.iloc[jj] > F.sma5.iloc[jj]), None)
        if j is None and i + MAXH < n:
            j = i + MAXH
        if j is None:
            t.update(status="보유" if i + 1 < n else "진입 예정", held=n - 1 - i)
            out.append(t); busy = 10 ** 9; break
        t.update(exit_signal_date=ks.index[j].date().isoformat(), held=j - i,
                 exit_why="종가 > 5일선" if F.close.iloc[j] > F.sma5.iloc[j] else f"{MAXH}거래일 만료")
        if j + 1 >= n or i + 1 >= n:
            t.update(status="청산 예정"); out.append(t); busy = 10 ** 9; break
        xd = ks.index[j + 1]
        t.update(exit_date=xd.date().isoformat(), exit=float(ks.Open.iloc[j + 1]), status="완료")
        t["ret"] = t["exit"] / t["entry"] - 1
        if "etf_entry" in t and xd in etf.index:
            t["etf_ret"] = float(etf.Open.loc[xd]) / t["etf_entry"] - 1
        out.append(t); busy = j
    return out


def status(ks, F, trades):
    r = F.iloc[-1]; d = F.index[-1].date().isoformat()
    thr_px = float(ks.Open.iloc[-1] * (1 - K * r.sigma))
    cond = [("전날 미국 S&P500", f"{100*r.us:+.2f}% ({r.us_date})", "≤ −1%", bool(r.us <= US_DROP)),
            ("코스피 캔들", f"{100*r.candle:+.2f}% = {r.z:+.2f}σ (σ {100*r.sigma:.2f}%)", "≤ −2σ", bool(r.z <= -K))]
    st = dict(date=d, cond=cond, close=float(r.close), sma5=float(r.sma5))
    last = trades[-1] if trades else None
    if last and last["status"] != "완료":
        st["mode"] = last["status"]; st["trade"] = last
        if last["status"] == "진입 예정":
            st["headline"] = "매수 신호 — 다음 거래일 시가 진입"
        elif last["status"] == "보유":
            pl = r.close / last["entry"] - 1
            st["headline"] = f"보유 중 {last['held']}일째 / {MAXH}일 — 코스피 기준 평가 {100*pl:+.2f}%"
            st["exit_check"] = f"코스피 종가 {r.close:,.2f} vs 5일선 {r.sma5:,.2f} → {'넘음' if r.close > r.sma5 else '아래'}"
        else:
            st["headline"] = f"청산 신호 ({last['exit_why']}) — 다음 거래일 시가 청산"
    else:
        st["mode"] = "대기"
        st["headline"] = "대기 — " + ("미국 −1% 급락 있었으나 코스피 2σ 음봉 아님" if r.us <= US_DROP else f"전날 미국 S&P {100*r.us:+.2f}% (급락 아님)")
    # 다음 거래일 감시: 방금 끝난 미국장 기준
    spx = load("GSPC").Close.pct_change()
    st["next_us"] = (spx.index[-1].date().isoformat(), float(spx.iloc[-1]))
    nsig = ks.Close.pct_change().rolling(60, min_periods=50).std().iloc[-1]
    st["next_sigma"] = float(nsig)
    return st


def dashboard(ks, F, trades, st, sigs):
    k0 = max(0, len(F) - 756)
    G, X = F.iloc[k0:], ks.iloc[k0:]
    num = lambda s: [None if v != v else round(float(v), 4) for v in s]
    taken = {t["signal_date"] for t in trades}
    payload = dict(d=[x.isoformat() for x in G.index.date], o=num(X.Open), h=num(X.High), l=num(X.Low), c=num(X.Close),
                   sma5=num(G.sma5), z=num(G.z), us=num(100 * G.us),
                   sig=[dict(d=F.index[i].date().isoformat(), y=float(F.close.iloc[i]), skip=F.index[i].date().isoformat() not in taken) for i in sigs if i >= k0],
                   ex=[dict(d=t["exit_signal_date"], y=float(F.close.loc[pd.Timestamp(t["exit_signal_date"])])) for t in trades
                       if t.get("exit_signal_date") and t["exit_signal_date"] >= str(G.index[0].date())])
    done = [t for t in trades if t["status"] == "완료"]
    def summ(L, key="ret"):
        L = [t for t in L if key in t]
        if not L:
            return "—"
        p = np.array([t[key] for t in L])
        return f"{len(L)}회 · 승률 {100*(p>0).mean():.0f}% · 평균 {100*p.mean():+.2f}% · 누적 {100*(np.prod(1+p)-1):+.1f}%"
    rows = []
    for t in reversed(trades):
        rows.append("<tr class='{}'><td>{}</td><td>S&amp;P {:+.2f}% / 캔들 {:+.2f}% ({:+.1f}σ)</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            "live" if t["live"] else "", t["signal_date"], 100 * t["us"], 100 * t["candle"], t["z"],
            f"{t.get('entry_date','')} {t['entry']:,.2f}" if "entry" in t else "—",
            f"{t.get('exit_date','')} {t['exit']:,.2f}" if "exit" in t else "—", t.get("exit_why", ""),
            f"{100*t['ret']:+.2f}%" if "ret" in t else t["status"], f"{100*t['etf_ret']:+.2f}%" if "etf_ret" in t else ""))
    cond_rows = "".join(f"<tr><td>{n}</td><td>{html.escape(v)}</td><td>{th}</td><td class='{'ok' if ok else 'no'}'>{'충족' if ok else '—'}</td></tr>" for n, v, th, ok in st["cond"])
    nu_d, nu = st["next_us"]
    nxt = f"<p class='sub'>다음 거래일 감시: 미국 {nu_d} S&amp;P {100*nu:+.2f}% → " + \
          (f"<b>−1% 이하 — 오늘 코스피가 시가 대비 {100*K*st['next_sigma']:.2f}% 이상 하락 마감하면 매수 신호</b>" if nu <= US_DROP else "급락 아님 (신호 없음)") + "</p>"
    extra = ""
    if st.get("trade"):
        t = st["trade"]
        extra = f"<p class='sub'>신호일 {t['signal_date']} · 미국 S&amp;P {100*t['us']:+.2f}% · 캔들 {t['z']:+.1f}σ" + \
                (f" · 진입 {t['entry_date']} {t['entry']:,.2f}" if "entry" in t else "") + "</p>"
        if st.get("exit_check"):
            extra += f"<p class='sub'>청산 확인: {st['exit_check']}</p>"
    page = TEMPLATE.replace("__DATA__", json.dumps(payload)).replace("__HEAD__", html.escape(st["headline"])).replace("__DATE__", st["date"]) \
        .replace("__MODE__", st["mode"]).replace("__EXTRA__", extra + nxt).replace("__COND__", cond_rows).replace("__ROWS__", "".join(rows)) \
        .replace("__BT__", summ([t for t in done if not t["live"]])).replace("__BTE__", summ([t for t in done if not t["live"]], "etf_ret")) \
        .replace("__LV__", summ([t for t in done if t["live"]])).replace("__GOLIVE__", GO_LIVE) \
        .replace("__GEN__", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    open(os.path.join(DOCS, "kospi.html"), "w", encoding="utf-8").write(page)


TEMPLATE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>코스피 반등 전략</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script src="charts.js"></script>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e1dc;--card:#fff;--ok:#1a7f4b;--no:#9a9a94;--acc:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#9b9a94;--line:#2c2c2a;--card:#1d1d1b;--ok:#4ade80;--no:#6b6b66;--acc:#fb923c}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:980px;margin:auto;padding:16px} nav a{color:var(--acc);margin-right:14px;font-size:14px;text-decoration:none} nav a.on{font-weight:700}
h1{font-size:18px;margin:8px 0 4px} .sub{color:var(--mut);font-size:13px;margin:2px 0} .sub b{color:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}
.head{font-size:20px;font-weight:650;margin:6px 0} .mode{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--acc);color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:13px} td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:500} .ok{color:var(--ok);font-weight:650} .no{color:var(--no)} tr.live td{background:rgba(194,65,12,.08)}
.scroll{overflow-x:auto} .scroll table{min-width:820px} .scroll td{white-space:nowrap} .chart{width:100%}
</style></head><body><main>
<nav><a href="index.html">나스닥 → NQ</a><a class="on" href="kospi.html">코스피 반등</a><a href="consensus.html">컨센서스</a></nav>
<h1>코스피 미국발 급락 → 반등 매수 <span class="sub">(관찰)</span></h1>
<p class="sub">기준일 __DATE__ (코스피 종가) · 생성 __GEN__ · 실전 검증 시작 __GOLIVE__</p>
<div class="card"><span class="mode">__MODE__</span><div class="head">__HEAD__</div>__EXTRA__
<p class="sub">진입 = 전날 미국 S&amp;P ≤ −1% 그리고 코스피 캔들 ≤ −2σ → 다음 날 시가 · 청산 = 코스피 종가 &gt; 5일선 다음 날 시가 (최대 10거래일)</p></div>
<div class="card"><b>오늘의 판단 근거</b><table><tr><th>조건</th><th>값</th><th>기준</th><th></th></tr>__COND__</table></div>
<div class="card"><b>지표 차트</b> <span class="sub">(▲ 매수 신호 · ▼ 청산 신호 · 점선 = 기준선 · 손가락으로 좌우 이동·확대)</span><div id="ch" class="chart"></div></div>
<div class="card"><b>거래 기록</b> <span class="sub">(코스피 지수 시가 기준, 비용 전)</span>
<p class="sub">백테스트(1997~): __BT__<br>KODEX200 실제 가격 (2002~): __BTE__<br>실전 검증: __LV__</p>
<div class="scroll"><table><tr><th>신호일</th><th>근거</th><th>진입</th><th>청산</th><th>청산 사유</th><th>코스피</th><th>KODEX200</th></tr>__ROWS__</table></div></div>
<p class="sub" style="text-align:right">차트: <a href="https://www.tradingview.com/" style="color:inherit">TradingView Lightweight Charts</a></p>
</main><script>
const D=__DATA__;const K=window.CHART_COLORS;
const mk=[...D.sig.filter(x=>!x.skip).map(x=>({time:x.d,position:'belowBar',color:K.acc,shape:'arrowUp',text:'매수'})),
 ...D.ex.map(x=>({time:x.d,position:'aboveBar',color:K.blue,shape:'arrowDown',text:'청산'}))];
buildStack(document.getElementById('ch'),{dates:D.d,defaultRange:'1Y',panes:[
 {title:'코스피',height:340,series:[{type:'candle',o:D.o,h:D.h,l:D.l,c:D.c,up:K.red,down:K.blue,digits:2},{type:'line',v:D.sma5,color:K.fg,width:1,name:'5일선',digits:2,lastValue:false}],markers:mk},
 {title:'코스피 캔들/σ',height:120,series:[{type:'hist',v:D.z,colorFn:v=>v<=-2?K.acc:K.gray,digits:2}],lines:[{value:-2}]},
 {title:'전날 미국 S&P %',height:130,series:[{type:'hist',v:D.us,colorFn:v=>v<=-1?K.acc:K.gray,digits:2}],lines:[{value:-1}]}]});
</script></body></html>"""


def main():
    ks, F, etf, sigs = compute()
    trades = replay(ks, F, etf, sigs)
    st = status(ks, F, trades)
    pd.DataFrame(trades).to_csv(os.path.join(ST, "kospi_trades.csv"), index=False, encoding="utf-8-sig")
    dashboard(ks, F, trades, st, sigs)
    sp = os.path.join(ST, "kospi_state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else {"sent": []}
    url = os.environ.get("PAGES_URL", "")
    link = f"\n<a href=\"{url}kospi.html\">코스피 대시보드</a>" if url else ""
    E = html.escape
    T = F.index[-1].date().isoformat()
    last = trades[-1] if trades else None
    cond = E("\n".join(f"{'✅' if ok else '▫️'} {n}: {v} ({th})" for n, v, th, ok in st["cond"]))
    evs = []
    if last and last["signal_date"] == T and last["status"] in ("진입 예정", "보유"):
        evs.append((f"entry:{T}", f"🟠 <b>코스피 매수 신호</b> ({T} 종가 기준, 관찰)\n미국 S&amp;P {100*last['us']:+.2f}% → 코스피 캔들 {100*last['candle']:+.2f}% ({last['z']:+.1f}σ)\n"
                                  f"실행: 다음 거래일 시가 매수 (코스피200 선물 / KODEX200)\n청산: 코스피 종가 &gt; 5일선 또는 {MAXH}거래일\n\n{cond}"))
    elif last and last.get("exit_signal_date") == T:
        evs.append((f"exit:{T}", f"🔵 <b>코스피 청산 신호</b> ({T})\n사유: {E(last['exit_why'])} (보유 {last['held']}거래일)\n"
                                 f"진입 {last.get('entry_date','')} {last.get('entry', float('nan')):,.2f} → 종가 {st['close']:,.2f}\n실행: 다음 거래일 시가 청산"))
    nu_d, nu = st["next_us"]
    if nu <= US_DROP and st["mode"] == "대기":
        evs.append((f"watch:{nu_d}", f"⚪️ <b>미국 급락 — 오늘 코스피 감시</b>\nS&amp;P {100*nu:+.2f}% ({nu_d})\n"
                                     f"오늘 코스피가 시가 대비 {100*K*st['next_sigma']:.2f}% 이상 하락 마감하면 매수 신호 (내일 아침 확정 알림)"))
    for key, msg in evs:
        if key not in S["sent"]:
            if telegram(msg + link) is not False:
                S["sent"] = (S["sent"] + [key])[-200:]
    S.update(last_run=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), basis_date=T, mode=st["mode"], headline=st["headline"])
    json.dump(S, open(sp, "w"), ensure_ascii=False, indent=1)
    if os.environ.get("TELEGRAM_TEST"):
        telegram(f"🧪 코스피 연결 테스트 — {E(st['headline'])}\n\n{cond}{link}")
    print(st["headline"])


if __name__ == "__main__":
    main()
