"""카드 v2 — 포트폴리오 위기 테스트"""
import base64, json, re
import pandas as pd
from v2 import page, chrome, K, OUT, H, ASSETS, W, HH

J = lambda p: json.loads((OUT / p).read_text())


def wk(t):
    d = J(f"etf_{t}.json" if t in ("SPY", "QQQ", "TLT", "GLD") else f"{t}.json")
    return pd.Series(d["wk"]["c"], index=pd.to_datetime(d["wk"]["d"]))


BT = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
df = pd.DataFrame({t: wk(t) for t in ["SPY", "QQQ", "TLT"] + BT}).ffill()
fx = J("fx.json")["krw"]
krw = pd.Series(fx["c"], index=pd.to_datetime(fx["d"])).reindex(df.index, method="ffill")
PF = [("빅테크 5", {t: .2 for t in BT}), ("S&P 500", {"SPY": 1}), ("나스닥 100", {"QQQ": 1}), ("주식 60 · 채권 40", {"SPY": .6, "TLT": .4})]
CR = {"2008": ("2007-10-09", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-10-12")}


def path(w, a, fxadj=False):
    x = df[df.index >= a]
    v = sum(w[t] * x[t] / x[t].iloc[0] for t in w)
    if fxadj:
        k = krw[krw.index >= a]
        v = v * k / k.iloc[0]
    return v


def test(w, c, fxadj=False):
    a, b = CR[c]
    v = path(w, a, fxadj)
    dd = v[v.index <= b].min() - 1
    r = v[(v.index > b) & (v >= 1)]
    return dd, (round((r.index[0] - v.index[0]).days / 30.44) if len(r) else None)


R = {(n, c): test(w, c) for n, w in PF for c in CR}
SPYK = {c: test({"SPY": 1}, c, True) for c in CR}
for k, v in R.items():
    print(k, f"{v[0] * 100:.1f}%", v[1])
print("SPY 원화", {c: (round(v[0] * 100, 1), v[1]) for c, v in SPYK.items()})


def line_svg(v, w=912, h=430, mark=True):
    v = v[v.index <= "2013-01-01"]
    ys = v.values
    lo, hi = ys.min(), max(ys.max(), 1.0)
    X = lambda i: i / (len(ys) - 1) * w
    Y = lambda y: (hi - y) / (hi - lo) * (h - 40) + 20
    pts = " ".join(f"{X(i):.1f},{Y(y):.1f}" for i, y in enumerate(ys))
    im = int(ys.argmin())
    yr = "".join(f'<text x="{X(i):.0f}" y="{h + 34}" font-size="24" font-weight="700" fill="{K["mut"]}" text-anchor="middle">{d.year}</text>'
                 for i, d in enumerate(v.index) if d.month == 1 and d.day <= 7)
    return (f'<svg width="{w}" height="{h + 44}" style="overflow:visible"><line x1="0" x2="{w}" y1="{Y(1):.1f}" y2="{Y(1):.1f}" stroke="{K["line"]}" stroke-width="3" stroke-dasharray="10 8"/>'
            f'<text x="{w * 0.42:.0f}" y="{Y(1) - 14:.1f}" font-size="26" font-weight="700" fill="{K["mut"]}" text-anchor="middle">처음 넣은 돈</text>'
            f'<polyline points="{pts}" fill="none" stroke="{K["ink"]}" stroke-width="6" stroke-linejoin="round"/>'
            f'<circle cx="{X(im):.1f}" cy="{Y(ys[im]):.1f}" r="16" fill="{K["or_"]}"/>'
            f'<text x="{X(im) + 30:.1f}" y="{Y(ys[im]) + 14:.1f}" font-size="58" font-weight="900" fill="{K["or_"]}">{(ys[im] - 1) * 100:.0f}%</text>{yr}</svg>')


def hbars(items, vmax, fmt, colors, lab_w=330):
    return "".join(f'<div style="display:grid;grid-template-columns:{lab_w}px 1fr;gap:20px;align-items:center;margin-top:56px">'
                   f'<div style="font-size:38px;font-weight:900">{n}</div>'
                   f'<div style="display:flex;align-items:center;gap:18px"><div style="height:88px;width:{max(abs(v) / vmax, .03) * 100 * .72:.0f}%;background:{c};border-radius:10px"></div>'
                   f'<b style="font-size:46px;font-weight:900;color:{c}">{fmt(v)}</b></div></div>' for (n, v), c in zip(items, colors))


def slides():
    spy08 = path({"SPY": 1}, CR["2008"][0])
    s1 = (f'<div class="eyebrow">포트폴리오 위기 테스트</div>'
          f'<div class="h" style="margin-top:50px">당신 포트폴리오,<br><span class="o">2008년</span>이었다면<br>몇 % 빠졌을까?</div>'
          f'<div style="margin-top:90px">{line_svg(spy08)}</div>'
          f'<div class="tiny" style="margin-top:6px">S&P 500에 2007년 10월 고점에 넣었다면 (달러 기준)</div>' + chrome(1, 6))
    it = sorted([(n, R[(n, "2008")][0]) for n, _ in PF], key=lambda x: x[1])
    cols = [K["or_"] if v < -0.4 else K["bl"] for _, v in it]
    s2 = (f'<div class="m">같은 위기,<br>담은 것에 따라<br><span class="o">반토막</span>과 <span class="b">−{-R[("주식 60 · 채권 40", "2008")][0] * 100:.0f}%</span></div>'
          f'<div style="margin-top:70px">{hbars(it, 0.6, lambda v: f"{v * 100:.0f}%", cols)}</div>'
          f'<div class="tiny" style="margin-top:40px">2008 금융위기: 2007-10-09 고점에서 2009-03-09 바닥까지, 시작 대비 가장 많이 빠졌을 때</div>' + chrome(2, 6))
    it3 = [(n, R[(n, "2008")][1]) for n, _ in PF]
    mx = max(v for _, v in it3)
    s3 = (f'<div class="m">다시 본전까지,<br>길게는 <span class="o">{mx // 12}년 {mx % 12}개월</span></div>'
          f'<div style="margin-top:70px">{hbars(it3, mx, lambda v: f"{v}개월", [K["or_"] if v == mx else K["ink"] for _, v in it3])}</div>'
          f'<div class="s" style="margin-top:60px">가장 많이 빠진 빅테크 5가 가장 빨리 돌아왔어요.<br>깊이와 회복 기간은 따로 봐야 해요.</div>' + chrome(3, 6))
    a8, a22 = R[("주식 60 · 채권 40", "2008")], R[("주식 60 · 채권 40", "2022")]
    b8, b22 = R[("S&P 500", "2008")], R[("S&P 500", "2022")]
    pair = lambda yr, x, y: (f'<div style="flex:1;background:rgba(255,255,255,.06);border-radius:24px;padding:34px"><div style="font-size:40px;font-weight:900">{yr}</div>'
                             f'<div style="margin-top:22px;font-size:28px;opacity:.6;font-weight:700">S&P 500</div><div style="font-size:64px;font-weight:900">{x[0] * 100:.0f}%</div>'
                             f'<div style="margin-top:14px;font-size:28px;opacity:.6;font-weight:700">주식 60 · 채권 40</div><div style="font-size:64px;font-weight:900" class="{"b" if x[0] < y[0] else "o"}">{y[0] * 100:.0f}%</div>'
                             f'<div style="margin-top:14px;font-size:26px;opacity:.6;font-weight:700">본전까지 {x[1]}개월 / {y[1]}개월</div></div>')
    s4 = (f'<div class="m">그런데 2022년엔<br><span class="o">채권도 같이 빠졌다</span></div>'
          f'<div style="display:flex;gap:26px;margin-top:70px">{pair("2008", b8, a8)}{pair("2022", b22, a22)}</div>'
          f'<div class="s" style="margin-top:50px">금리가 빠르게 오르면 채권값도 떨어져요.<br>방패가 매번 같은 방패는 아니에요.</div>' + chrome(4, 6))
    u, k = R[("S&P 500", "2008")], SPYK["2008"]
    f0, f1 = krw[krw.index >= CR["2008"][0]].iloc[0], krw[(krw.index >= CR["2008"][0]) & (krw.index <= CR["2008"][1])].max()
    s5 = (f'<div class="eyebrow">한국 투자자라면</div>'
          f'<div class="m" style="margin-top:40px">원화로 보면<br>2008년은 달랐다</div>'
          f'<div style="display:flex;gap:40px;margin-top:80px;align-items:flex-end">'
          f'<div style="flex:1"><div style="font-size:32px;font-weight:800;opacity:.6">S&P 500, 달러로</div><div style="font-size:150px;font-weight:900;letter-spacing:-0.06em;line-height:1.05">{u[0] * 100:.0f}%</div></div>'
          f'<div style="flex:1"><div style="font-size:32px;font-weight:800;opacity:.6">원화로</div><div style="font-size:150px;font-weight:900;letter-spacing:-0.06em;line-height:1.05" class="o">{k[0] * 100:.0f}%</div></div></div>'
          f'<div class="s" style="margin-top:60px">같은 기간 환율 {f0:,.0f}원 → 최고 {f1:,.0f}원.<br>위기 때 달러가 올라 쿠션이 됐어요.<br>2020년엔 그 쿠션이 거의 없었어요 (달러 {SPYK["2020"][0] * 0 + R[("S&P 500", "2020")][0] * 100:.0f}% · 원화 {SPYK["2020"][0] * 100:.0f}%).</div>'
          + chrome(5, 6))
    s6 = (f'<div class="m">내 포트폴리오도<br>돌려 보세요</div>'
          + "".join(f'<div style="display:flex;gap:28px;align-items:baseline;margin-top:{60 if i == 1 else 34}px"><b class="o" style="font-size:72px;font-weight:900">{i}</b>'
                    f'<div><div style="font-size:50px;font-weight:900">{a}</div><div style="font-size:30px;opacity:.6;font-weight:600;margin-top:6px">{b}</div></div></div>'
                    for i, (a, b) in enumerate([("위기 3구간", "2008 · 2020 · 2022에 얼마나 빠졌나"), ("본전까지", "다시 돌아오는 데 몇 달 걸렸나"), ("원화 기준", "환율까지 넣으면 어땠나")], 1))
          + f'<div style="margin-top:70px;background:{K["ink"]};color:{K["cream"]};border-radius:24px;padding:30px 36px;font-size:36px;font-weight:800">tickermap.kr — 포트폴리오 3개까지, 무료로</div>'
          f'<div class="tiny" style="margin-top:28px">위기 시작일에 사서 그대로 둔 경우(리밸런싱 없음) · 주간 수정종가(배당 재투자 반영) · 하락 = 시작 대비 구간 안 최저 · 빅테크 5 = 애플·마이크로소프트·알파벳·아마존·엔비디아 같은 비중(지금 기준으로 고른 이름이라 과거엔 알 수 없던 구성) · 주식 60 · 채권 40 = SPY 60%, TLT(미국 장기 국채) 40% · 원화 = 주간 원/달러 환율 반영 · 출처: 주가·환율 시세, 티커맵 계산 · 기준일 2026-10-23<br>과거 기록이며 앞날을 뜻하지 않아요. 정보 제공용이며 투자 권유가 아닙니다.</div>'
          + chrome(6, 6))
    return {"01": (s1, None, None), "02": (s2, None, None), "03": (s3, None, None), "04": (s4, K["dark"], K["cream"]), "05": (s5, None, None), "06": (s6, None, None)}


def main():
    from playwright.sync_api import sync_playwright
    font = base64.b64encode((ASSETS / "PretendardVariable.woff2").read_bytes()).decode()
    S = slides()
    txt = lambda s: re.sub(r"<[^>]+>", "", s)
    allt = " ".join(txt(v[0]) for v in S.values())
    print("금지:", [w for w in H["banned"] if w in allt] or "없음", "| 마지막 장 누락:", [w for w in H["required_last_slide"] if w not in txt(S["06"][0])] or "없음")
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": W, "height": HH})
        for k, (body, bg, ink) in S.items():
            pg.set_content(page(body, font, bg, ink))
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(OUT / f"v2pf_{k}.png"))
        br.close()


main()
