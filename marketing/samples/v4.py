"""카드 v4 — 토스피드 원칙: 본문에 제품 없음, 티커맵은 데이터 출처와 끝 한 줄의 '도구 안내'로만. 연재명 = 브랜드."""
import base64, json, re
import pandas as pd
from v2 import page, K, OUT, H, ASSETS, W, HH, LOGO

J = lambda p: json.loads((OUT / p).read_text())
ETF = ("SPY", "QQQ", "SMH", "VOO")
SERIES = "흔한 착각"


def px(t):
    d = J(f"etf_{t}.json" if t in ETF else f"{t}.json")["px"]
    return pd.Series(d["c"], index=pd.to_datetime(d["d"]))


def foot(i, n):
    # 브랜드는 작게: 연재명 + 데이터 출처
    return (f'<div style="position:absolute;left:84px;right:84px;bottom:66px;display:flex;justify-content:space-between;align-items:center;font-size:24px;font-weight:700;opacity:.5">'
            f'<span style="display:flex;align-items:center;gap:10px">{LOGO.format(s=26)}{SERIES} · 데이터 티커맵</span><span>{i}/{n}</span></div>')


def tag(no):
    return f'<div style="display:inline-block;font-size:28px;font-weight:800;padding:10px 22px;border-radius:999px;border:3px solid currentColor;opacity:.75">{SERIES} {no:02d}</div>'


def build():
    N = 8
    DAY, UP = "2025-01-27", "2025-04-09"
    w = {"VOO": .25, "QQQ": .25, "SMH": .25, "NVDA": .25}
    df = pd.DataFrame({t: px(t) for t in list(w) + ["SPY"]}).dropna()
    R = df.pct_change()
    pf = lambda d: sum(R.loc[d, t] * v for t, v in w.items())
    dn_me, dn_sp, up_me, up_sp = pf(DAY), R.loc[DAY, "SPY"], pf(UP), R.loc[UP, "SPY"]
    hold = {e: J(f"etf_{e}.json")["holdings"] for e in ("VOO", "QQQ", "SMH")}
    ex = {}
    for e, hs in hold.items():
        for h in hs:
            ex[h[0]] = ex.get(h[0], 0) + w[e] * h[2] / 100
    ex["NVDA"] += w["NVDA"]
    nv = ex["NVDA"]
    print(f"하락일 {dn_me:.4f} vs {dn_sp:.4f} | 상승일 {up_me:.4f} vs {up_sp:.4f} | 엔비디아 {nv:.3f}")

    S = {}
    S["01"] = (f'{tag(1)}'
               f'<div class="h" style="margin-top:70px;font-size:112px">4개로<br>나눠 담았는데,<br><span class="o">왜 나만</span><br>더 빠졌을까?</div>'
               f'<div class="s" style="margin-top:60px">분산했다고 믿었던 계좌의 속을 열어 봤어요.</div>' + foot(1, N), None, None)

    big = lambda lab, v, c: (f'<div style="flex:1"><div style="font-size:34px;font-weight:800;opacity:.6">{lab}</div>'
                             f'<div style="font-size:130px;font-weight:900;letter-spacing:-0.06em;line-height:1.05;color:{c}">{v * 100:+.1f}%</div></div>')
    S["02"] = (f'<div class="eyebrow">2025년 1월 27일, 같은 하루</div>'
               f'<div style="display:flex;gap:30px;margin-top:80px">{big("4개로 나눈 계좌", dn_me, K["bl"])}{big("S&P 500 하나", dn_sp, K["mut"])}</div>'
               f'<div class="m" style="margin-top:90px">나눠 담은 쪽이<br><span class="b">{dn_me / dn_sp:.1f}배</span> 더 빠졌어요</div>'
               + "".join(f'<div style="margin-top:{60 if i == 0 else 28}px"><div style="font-size:30px;font-weight:800;opacity:.6;margin-bottom:10px">{lab}</div>'
                         f'<div style="height:90px;width:{abs(v) / abs(dn_me) * 100:.0f}%;background:{c};border-radius:14px"></div></div>'
                         for i, (lab, v, c) in enumerate([("4개로 나눈 계좌", dn_me, K["bl"]), ("S&P 500 하나", dn_sp, K["mut"])]))
               + foot(2, N), None, None)

    chip = lambda a, b: (f'<div style="background:#fff;border-radius:26px;padding:30px 34px;box-shadow:0 12px 28px rgba(0,0,0,.07)">'
                         f'<div style="font-size:30px;font-weight:700;opacity:.55">{b}</div><div style="font-size:52px;font-weight:900;margin-top:6px">{a} <span class="o" style="font-size:40px">25%</span></div></div>')
    S["03"] = (f'<div class="eyebrow">직장인 민수 씨(예시)의 계좌</div>'
               f'<div class="m" style="margin-top:40px">"몰빵은 무서우니까<br>4개로 나눴죠"</div>'
               f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:80px">'
               f'{chip("VOO", "S&P 500 ETF")}{chip("QQQ", "나스닥 100 ETF")}{chip("SMH", "반도체 ETF")}{chip("NVDA", "엔비디아")}</div>'
               f'<div class="s" style="margin-top:60px">그날은 딥시크 쇼크로 엔비디아가 하루에 {R.loc[DAY, "NVDA"] * 100:.0f}% 빠진 날이었어요.</div>' + foot(3, N), None, None)

    top = sorted(ex.items(), key=lambda x: -x[1])[:5]
    KO = {"NVDA": "엔비디아", "AAPL": "애플", "MU": "마이크론", "MSFT": "마이크로소프트", "AMD": "AMD", "TSM": "TSMC", "AVGO": "브로드컴"}
    rows = "".join(f'<div style="display:grid;grid-template-columns:270px 1fr 150px;gap:18px;align-items:center;margin-top:{28 if i else 0}px">'
                   f'<div style="font-size:{46 if i == 0 else 34}px;font-weight:900">{KO.get(t, t)}</div>'
                   f'<div style="height:{84 if i == 0 else 40}px;background:{K["or_"] if i == 0 else "#3a3934"};border-radius:10px;width:{max(v / top[0][1], .03) * 100:.0f}%"></div>'
                   f'<div style="font-size:{64 if i == 0 else 36}px;font-weight:900;text-align:right" class="{"o" if i == 0 else ""}">{v * 100:.0f}%</div></div>' for i, (t, v) in enumerate(top))
    S["04"] = (f'<div class="m">ETF 속까지 펼쳐 보니<br>계좌의 <span class="o">3분의 1</span>이<br>엔비디아였어요</div>'
               f'<div style="margin-top:90px">{rows}</div>'
               f'<div class="s" style="margin-top:70px;opacity:.75">이름은 4개, 실제로는 엔비디아 한 종목에<br>크게 걸려 있던 거예요.</div>' + foot(4, N), K["dark"], K["cream"])

    NM = {"VOO": "S&P 500", "QQQ": "나스닥 100", "SMH": "반도체"}
    blocks = ""
    for e, hs in hold.items():
        items = "".join(f'<div style="display:flex;justify-content:space-between;padding:7px 0;border-top:2px solid {K["line"]};font-size:29px;font-weight:{900 if h[0] == "NVDA" else 600}">'
                        f'<span class="{"o" if h[0] == "NVDA" else ""}">{i}. {KO.get(h[0], h[0])}</span><span class="{"o" if h[0] == "NVDA" else ""}">{h[2]:.1f}%</span></div>'
                        for i, h in enumerate(hs[:3], 1))
        blocks += f'<div style="background:#fff;border-radius:24px;padding:20px 30px;margin-top:16px"><div style="font-size:28px;font-weight:900;margin-bottom:6px">{NM[e]} ETF ({e}) 상위 3</div>{items}</div>'
    S["05"] = (f'<div class="m">왜 그럴까?<br>ETF의 <span class="o">1등이 겹쳐서</span>예요</div>'
               f'<div style="margin-top:40px">{blocks}</div>'
               f'<div class="s" style="margin-top:36px">시가총액이 큰 종목은 여러 ETF에 동시에 크게 들어가요.</div>' + foot(5, N), None, None)

    S["06"] = (f'<div class="eyebrow">그럼 쏠리면 늘 나쁠까?</div>'
               f'<div class="m" style="margin-top:40px">오르는 날엔<br><span class="o">더 크게</span> 올랐어요</div>'
               f'<div style="display:flex;gap:30px;margin-top:70px">{big("4개로 나눈 계좌", up_me, K["or_"])}{big("S&P 500 하나", up_sp, K["mut"])}</div>'
               f'<div class="tiny" style="margin-top:6px;font-size:26px">2025년 4월 9일, 관세 유예 발표 날</div>'
               f'<div class="s" style="margin-top:60px">쏠림 자체가 문제가 아니라,<br><b style="opacity:1">모르고 쏠려 있는 게</b> 문제예요.</div>' + foot(6, N), None, None)

    steps = [("담은 ETF마다 상위 10개 종목 적기", "운용사 홈페이지나 ETF 정보 사이트에 나와요"),
             ("같은 종목 비중 더하기", "ETF 비중 × 그 안의 종목 비중"),
             ("1등 종목이 생각보다 크다면", "알고 고른 쏠림인지 한 번 더 생각하기")]
    S["07"] = (f'<div class="m">내 계좌도<br>3분이면 확인해요</div>'
               + "".join(f'<div style="display:flex;gap:28px;align-items:baseline;margin-top:{64 if i == 1 else 38}px"><b class="o" style="font-size:72px;font-weight:900">{i}</b>'
                         f'<div><div style="font-size:48px;font-weight:900">{a}</div><div style="font-size:30px;opacity:.6;font-weight:600;margin-top:6px">{b}</div></div></div>'
                         for i, (a, b) in enumerate(steps, 1))
               + f'<div class="s" style="margin-top:80px">저장해 두고 리밸런싱할 때 꺼내 보세요.</div>' + foot(7, N), None, None)

    S["08"] = (f'<div class="m" style="font-size:64px">숫자는 이렇게 만들었어요</div>'
               f'<div style="margin-top:40px;font-size:28px;line-height:1.65;opacity:.75;font-weight:600">'
               f'· 하루 수익률: 그날 종가 기준, 네 개를 25%씩 들고 있던 경우<br>'
               f'· 실제 비중: 각 ETF의 상위 보유 종목 비중 × ETF 비중을 더한 값. 2026-10-23 기준 보유 비중이라 2025년 당시와 조금 다를 수 있어요<br>'
               f'· 민수 씨는 예시 인물이에요<br>'
               f'· 출처: 주가 시세, ETF 운용사 공개 보유 종목, 티커맵 계산 · 기준일 2026-10-23</div>'
               f'<div style="margin-top:50px;font-size:30px;font-weight:700;opacity:.8">과거 기록이며 앞날을 뜻하지 않아요. 정보 제공용이며 투자 권유가 아닙니다.</div>'
               f'<div style="margin-top:90px;border-top:3px solid {K["line"]};padding-top:40px;font-size:34px;font-weight:800">직접 계산해 보기 <span style="opacity:.55;font-weight:600">— 티커맵 포트폴리오에 비중을 넣으면 ETF 속 겹침을 합쳐 보여 줘요 (무료)</span></div>'
               + foot(8, N), None, None)
    return S


def main():
    from playwright.sync_api import sync_playwright
    font = base64.b64encode((ASSETS / "PretendardVariable.woff2").read_bytes()).decode()
    S = build()
    txt = lambda s: re.sub(r"<[^>]+>", "", s)
    allt = " ".join(txt(v[0]) for v in S.values())
    print("금지:", [w for w in H["banned"] if w in allt] or "없음", "| 마지막 장 누락:", [w for w in H["required_last_slide"] if w not in txt(S["08"][0])] or "없음",
          "| '티커맵' 언급 장:", [k for k, v in S.items() if "티커맵" in txt(v[0]).replace("데이터 티커맵", "")])
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": W, "height": HH})
        for k, (body, bg, ink) in S.items():
            pg.set_content(page(body, font, bg, ink))
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(OUT / f"v4_{k}.png"))
        br.close()


main()
