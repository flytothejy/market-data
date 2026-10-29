"""카드 v3 — '내 일처럼': 상황 → 공감 → 실제 데이터로 드러나는 사실 → 티커맵이 보여 주는 것 → 행동"""
import base64, json, re
import pandas as pd
from v2 import page, chrome, K, OUT, H, ASSETS, W, HH

J = lambda p: json.loads((OUT / p).read_text())
ETF = ("SPY", "QQQ", "SMH", "VOO", "TLT", "GLD", "SOXX", "SCHD")


def img64(p):
    return "data:image/png;base64," + base64.b64encode((OUT / p).read_bytes()).decode()


def phone(src, w=520, h=None, top=0):
    hh = f"height:{h}px;" if h else ""
    return (f'<div style="width:{w}px;{hh}border-radius:46px;background:#151513;padding:14px;box-shadow:0 30px 60px rgba(0,0,0,.18)">'
            f'<div style="border-radius:34px;overflow:hidden;{f"height:{h - 28}px;" if h else ""}background:#fff">'
            f'<img src="{src}" style="width:100%;display:block;margin-top:-{top}px"></div></div>')


def shot(src, w, h, top=0, r=24):
    return (f'<div style="width:{w}px;height:{h}px;border-radius:{r}px;overflow:hidden;background:#fff;box-shadow:0 18px 40px rgba(0,0,0,.14)">'
            f'<img src="{src}" style="width:100%;display:block;margin-top:-{top}px"></div>')


def cta(title, items, btn, basis, n):
    return (f'<div class="m">{title}</div>'
            + "".join(f'<div style="display:flex;gap:28px;align-items:baseline;margin-top:{56 if i == 1 else 30}px"><b class="o" style="font-size:68px;font-weight:900">{i}</b>'
                      f'<div><div style="font-size:48px;font-weight:900">{a}</div><div style="font-size:30px;opacity:.6;font-weight:600;margin-top:6px">{b}</div></div></div>'
                      for i, (a, b) in enumerate(items, 1))
            + f'<div style="margin-top:64px;background:{K["ink"]};color:{K["cream"]};border-radius:24px;padding:30px 36px;font-size:36px;font-weight:800">{btn}</div>'
            f'<div class="tiny" style="margin-top:26px">{basis}<br>정보 제공용이며 투자 권유가 아닙니다.</div>' + chrome(n, n))


# ================================================================ A. 나눠 담았는데 왜 이렇게 빠졌지
def px(t):
    d = J(f"etf_{t}.json" if t in ETF else f"{t}.json")["px"]
    return pd.Series(d["c"], index=pd.to_datetime(d["d"]))


def set_a():
    DAY = "2025-01-27"
    w = {"VOO": .25, "QQQ": .25, "SMH": .25, "NVDA": .25}
    df = pd.DataFrame({t: px(t) for t in list(w) + ["SPY"]}).dropna()
    r = df.pct_change().loc[DAY]
    mine = sum(r[t] * v for t, v in w.items())
    spy = r["SPY"]
    AMT = 3000                                                     # 만 원
    hold = {e: {h[0]: h[2] / 100 for h in J(f"etf_{e}.json")["holdings"]} for e in ("VOO", "QQQ", "SMH")}
    ex = {}
    for e in hold:
        for k, v in hold[e].items():
            ex[k] = ex.get(k, 0) + w[e] * v
    ex["NVDA"] = ex.get("NVDA", 0) + w["NVDA"]
    top = sorted(ex.items(), key=lambda x: -x[1])[:6]
    KO = {"NVDA": "엔비디아", "AAPL": "애플", "MU": "마이크론", "MSFT": "마이크로소프트", "AMD": "AMD", "TSM": "TSMC", "AVGO": "브로드컴", "AMZN": "아마존"}
    print("A:", DAY, "민수", round(mine * 100, 2), "S&P", round(spy * 100, 2), "엔비디아 실제", round(ex["NVDA"] * 100, 1))

    acct = (f'<div style="margin-top:70px;background:#fff;border-radius:36px;padding:44px 48px;box-shadow:0 24px 50px rgba(0,0,0,.10)">'
            f'<div style="font-size:30px;font-weight:700;opacity:.55">내 계좌 · 오늘</div>'
            f'<div style="font-size:120px;font-weight:900;letter-spacing:-0.05em;color:{K["bl"]};line-height:1.1;margin-top:10px">−{-mine * AMT:,.0f}만 원</div>'
            f'<div style="font-size:44px;font-weight:800;color:{K["bl"]}">{mine * 100:.1f}% · 하루 만에</div>'
            f'<div style="display:flex;gap:14px;margin-top:34px">' + "".join(
                f'<span style="font-size:28px;font-weight:800;padding:10px 20px;border-radius:14px;background:#eef3fc;color:{K["bl"]}">{t} {r[t] * 100:.1f}%</span>' for t in w) + '</div></div>')
    s1 = (f'<div class="h" style="font-size:104px">하루 만에<br>계좌가 <span class="b">파랗게</span><br>녹아내린 날,</div>'
          f'<div class="m" style="margin-top:20px;opacity:.55">다들 한 번쯤 있죠</div>' + acct + chrome(1, 6))

    chip = lambda a, b: (f'<div style="background:#fff;border-radius:26px;padding:30px 34px;box-shadow:0 12px 28px rgba(0,0,0,.07)">'
                         f'<div style="font-size:30px;font-weight:700;opacity:.55">{b}</div><div style="font-size:52px;font-weight:900;margin-top:6px">{a}</div>'
                         f'<div style="font-size:40px;font-weight:900;margin-top:6px" class="o">25%</div></div>')
    s2 = (f'<div class="eyebrow">직장인 민수 씨, 미국 주식 3년 차</div>'
          f'<div class="m" style="margin-top:40px">"한 종목 몰빵은 위험하니까<br><span class="o">4개로 나눠 담았어요</span>"</div>'
          f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:80px">'
          f'{chip("VOO", "S&P 500 ETF")}{chip("QQQ", "나스닥 100 ETF")}{chip("SMH", "반도체 ETF")}{chip("NVDA", "엔비디아")}</div>'
          f'<div class="s" style="margin-top:60px">ETF 3개에 개별주 1개. 이 정도면 분산했다고 생각했죠.</div>' + chrome(2, 6))

    bar = lambda lab, sub, v, c: (f'<div style="margin-top:50px"><div style="display:flex;justify-content:space-between;align-items:baseline">'
                                  f'<div><span style="font-size:46px;font-weight:900">{lab}</span> <span style="font-size:30px;font-weight:700;opacity:.55">{sub}</span></div>'
                                  f'<b style="font-size:64px;font-weight:900;color:{c}">−{-v * AMT:,.0f}만 원</b></div>'
                                  f'<div style="height:70px;margin-top:16px;background:{K["line"]};border-radius:14px"><div style="height:70px;width:{abs(v) / abs(mine) * 100:.0f}%;background:{c};border-radius:14px"></div></div></div>')
    s3 = (f'<div class="eyebrow">2025년 1월 27일, 딥시크 쇼크</div>'
          f'<div class="m" style="margin-top:40px">같은 {AMT // 1000 * 1000:,}만 원, 같은 날</div>'
          + bar("민수 씨", "4개로 나눠 담음", mine, K["bl"])
          + bar("지영 씨", "S&P 500 하나만", spy, K["mut"])
          + f'<div style="font-size:150px;font-weight:900;letter-spacing:-0.06em;margin-top:70px" class="b">{mine / spy:.1f}배</div>'
          f'<div class="s" style="margin-top:0">"나눠 담았는데, 왜 내가 더 빠졌지?"</div>' + chrome(3, 6))

    mx = top[0][1]
    rows = "".join(f'<div style="display:grid;grid-template-columns:260px 1fr 150px;gap:18px;align-items:center;margin-top:{26 if i else 0}px">'
                   f'<div style="font-size:{44 if i == 0 else 34}px;font-weight:900">{KO.get(t, t)}</div>'
                   f'<div style="height:{80 if i == 0 else 40}px;background:{K["or_"] if i == 0 else "#3a3934"};border-radius:10px;width:{max(v / mx, .03) * 100:.0f}%"></div>'
                   f'<div style="font-size:{60 if i == 0 else 36}px;font-weight:900;text-align:right" class="{"o" if i == 0 else ""}">{v * 100:.0f}%</div></div>' for i, (t, v) in enumerate(top))
    s4 = (f'<div class="m">ETF 속까지 펼쳐 보니,<br>계좌의 <span class="o">3분의 1</span>이<br>엔비디아였어요</div>'
          f'<div style="margin-top:80px">{rows}</div>'
          f'<div class="s" style="margin-top:60px;opacity:.75">S&P 500에도, 나스닥 100에도, 반도체 ETF에도<br>1등은 엔비디아. 이름만 4개였던 거예요.</div>' + chrome(4, 6))

    feat = lambda t, d, v: (f'<div style="display:flex;justify-content:space-between;align-items:center;background:#fff;border-radius:26px;padding:30px 36px;margin-top:22px;box-shadow:0 12px 28px rgba(0,0,0,.07)">'
                            f'<div><div style="font-size:42px;font-weight:900">{t}</div><div style="font-size:28px;font-weight:600;opacity:.55;margin-top:6px">{d}</div></div>'
                            f'<div style="font-size:46px;font-weight:900" class="o">{v}</div></div>')
    s5 = (f'<div class="m">티커맵에 4개만 넣으면<br>바로 보여요</div>'
          f'<div style="margin-top:60px">'
          + feat("실제 노출", "ETF 속 종목까지 합친 진짜 비중", f"엔비디아 {ex['NVDA'] * 100:.0f}%")
          + feat("쏠림 경고", "한 종목·한 업종에 몰렸는지", "반도체 쏠림")
          + feat("위기 테스트", "2008 · 2020 · 2022에 얼마나 빠졌나", "3구간")
          + feat("원화 기준", "환율까지 넣은 내 돈 기준 성과", "₩")
          + f'</div><div class="s" style="margin-top:50px">계좌를 연결할 필요 없어요. 비중만 넣으면 돼요.</div>' + chrome(5, 6))
    s6 = cta("내 포트폴리오,<br>진짜로 나눠져 있을까?",
             [("담은 종목·ETF와 비중 입력", "로그인하면 3개까지 저장"), ("실제 노출 확인", "ETF 속 1등이 겹치지 않는지"), ("위기 때 얼마나 빠졌는지", "원화 기준으로")],
             "tickermap.kr — 포트폴리오 점검, 무료로",
             f"하루 수익률 = {DAY} 종가 기준, 같은 비중으로 들고 있던 경우 · 실제 노출 = 각 ETF의 지금 상위 보유 종목 비중 × ETF 비중 합 (2026-10-23 기준일, 그날의 보유 비중과 다를 수 있음) · 민수·지영은 예시 인물 · 출처: 주가 시세, ETF 운용사 공개 보유 종목, 티커맵 계산",
             6)
    return {"01": (s1, None, None), "02": (s2, None, None), "03": (s3, None, None), "04": (s4, K["dark"], K["cream"]), "05": (s5, None, None), "06": (s6, None, None)}


# ================================================================ B. 종목 하나 알아보려다 하루가 간다
def set_b():
    tabs = [("증권사 앱", "주가"), ("해외 금융 사이트", "실적 · 영어"), ("SEC 공시", "재무제표 · 영어"), ("뉴스 검색", "왜 빠졌지?"), ("커뮤니티", "내부자가 팔았대"), ("유튜브", "전망 영상 3개")]
    stack = "".join(f'<div style="position:relative;margin-top:{0 if i == 0 else -30}px;margin-left:{i * 34}px;width:720px;background:#fff;border-radius:22px;'
                    f'padding:28px 34px;box-shadow:0 10px 30px rgba(0,0,0,.10);display:flex;justify-content:space-between;align-items:center;z-index:{i}">'
                    f'<div style="display:flex;align-items:center;gap:16px"><span style="width:18px;height:18px;border-radius:50%;background:{K["line"]}"></span>'
                    f'<b style="font-size:36px">{a}</b></div><span style="font-size:28px;font-weight:700;opacity:.55">{b}</span></div>' for i, (a, b) in enumerate(tabs))
    s1 = (f'<div class="h" style="font-size:100px">엔비디아 하나<br>알아보려고<br>탭 <span class="o">몇 개</span> 여셨어요?</div>'
          f'<div style="margin-top:80px">{stack}</div>' + chrome(1, 6))
    s2 = (f'<div class="m" style="margin-top:30px">주가는 여기,<br>실적은 저기,<br>재무제표는 영어로.</div>'
          f'<div class="m o" style="margin-top:70px">찾다 보면<br>정작 생각할 시간이 없어요.</div>' + chrome(2, 6))
    hero = img64("site_hero.png")
    s3 = (f'<div style="display:flex;gap:40px;align-items:flex-start">'
          f'<div style="flex:1;padding-top:20px"><div class="m" style="font-size:76px">티커맵은<br><span class="o">한 장</span>에<br>한국어로</div>'
          f'<div class="s" style="margin-top:40px;font-size:34px">주가 · 실적 · 재무 · 공시 · 유명 투자자 · 내부자까지 한 페이지</div></div>'
          f'<div>{phone(hero, 470, 1060)}</div></div>' + chrome(3, 6))
    s4 = (f'<div class="m">맨 위 한 줄이<br>먼저 알려 줘요</div>'
          f'<div style="margin-top:50px;background:#fff;border-radius:30px;padding:40px 44px;box-shadow:0 18px 40px rgba(0,0,0,.10);font-size:44px;font-weight:800;line-height:1.45">'
          f'매출 +83% 고성장, 영업이익률 개선(+7.1%p). <span class="o">다만 90일 내부자 매도 $10억.</span></div>'
          f'<div class="s" style="margin-top:40px">좋은 점만, 나쁜 점만이 아니라 같이.<br>아래 점검표에서 하나씩 근거를 확인해요.</div>'
          f'<div style="margin-top:40px">{shot(hero, 912, 420, top=828, r=26)}</div>' + chrome(4, 6))
    er, etf, g13 = img64("site_er.png"), img64("site_etf.png"), img64("site_g13.png")
    lab = lambda t: f'<div style="font-size:30px;font-weight:900;margin:0 0 12px 4px">{t}</div>'
    s5 = (f'<div class="m">혼자서는 찾기 힘든 것까지</div>'
          f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:50px">'
          f'<div>{lab("실적 발표 때 주가는?")}{shot(er, 443, 420, top=240)}</div>'
          f'<div>{lab("이 종목 담은 ETF는?")}{shot(etf, 443, 420, top=0)}</div>'
          f'<div style="grid-column:1/3">{lab("유명 투자자는 늘렸나 줄였나?")}{shot(g13, 912, 330, top=0)}</div></div>' + chrome(5, 6))
    s6 = cta("검색창에<br>티커만 넣으세요",
             [("미국 주식 1,035개", "S&P 500 · 나스닥 100 · 주요 ETF"), ("매일 자동 업데이트", "SEC 공시 원문 기준"), ("한국어 · 무료", "가입 없이 바로")],
             "tickermap.kr",
             "화면: tickermap.kr 엔비디아 페이지 실제 캡처 (2026-10-23 종가 기준일) · 출처: SEC 공시(EDGAR), 13F·Form 4, 컨센서스·주가 시세, 티커맵 계산",
             6)
    return {"01": (s1, None, None), "02": (s2, K["dark"], K["cream"]), "03": (s3, None, None), "04": (s4, None, None), "05": (s5, None, None), "06": (s6, None, None)}


def main():
    from playwright.sync_api import sync_playwright
    font = base64.b64encode((ASSETS / "PretendardVariable.woff2").read_bytes()).decode()
    txt = lambda s: re.sub(r"<[^>]+>", "", s)
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": W, "height": HH})
        for name, S in [("v3a", set_a()), ("v3b", set_b())]:
            allt = " ".join(txt(v[0]) for v in S.values())
            last = txt(list(S.values())[-1][0])
            print(name, "금지:", [w for w in H["banned"] if w in allt] or "없음", "| 마지막 장 누락:", [w for w in H["required_last_slide"] if w not in last] or "없음")
            for k, (body, bg, ink) in S.items():
                pg.set_content(page(body, font, bg, ink))
                pg.wait_for_timeout(200)
                pg.screenshot(path=str(OUT / f"{name}_{k}.png"))
        br.close()


main()
