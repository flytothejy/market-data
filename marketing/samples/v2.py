"""카드 v2 — '한 세트 = 한 문장 이야기'. 장마다 한 문장 + 숫자 하나 + 그림 하나."""
import base64, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hub.cards import LOGO, ASSETS

OUT = Path(__file__).parent / "data"   # 사이트 JSON을 여기에 받아 두고 실행 (README)
H = json.loads(ROOT / "marketing" / "headlines.json".read_text())
SP = json.loads(ROOT / "hub" / "spec" / "tickermap_spec.json".read_text())["dividend"]
MS = json.loads((OUT / "MSFT.json").read_text())
K = dict(bg="#f3efe6", ink="#151513", mut="#77736a", line="#dcd6c8", or_="#e2531a", bl="#2463c4", dark="#151513", cream="#f3efe6")
W, HH = 1080, 1350


def page(body, font, bg=None, ink=None):
    bg, ink = bg or K["bg"], ink or K["ink"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:P;src:url(data:font/woff2;base64,{font}) format('woff2');font-weight:45 920}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{HH}px;background:{bg};color:{ink};font-family:P;letter-spacing:-0.035em;overflow:hidden}}
.w{{position:relative;width:{W}px;height:{HH}px;padding:80px 84px}}
.brand{{position:absolute;left:84px;bottom:70px;display:flex;align-items:center;gap:12px;font-size:30px;font-weight:800}}
.pg{{position:absolute;right:84px;bottom:74px;font-size:26px;font-weight:700;opacity:.5}}
.eyebrow{{font-size:34px;font-weight:800;opacity:.6}}
.h{{font-size:118px;line-height:1.08;font-weight:900;letter-spacing:-0.055em}}
.m{{font-size:84px;line-height:1.14;font-weight:900;letter-spacing:-0.05em}}
.s{{font-size:38px;line-height:1.45;font-weight:600;opacity:.7}}
.o{{color:{K['or_']}}} .b{{color:{K['bl']}}}
.tiny{{font-size:22px;line-height:1.55;opacity:.55;font-weight:500}}
</style></head><body><div class="w">{body}</div></body></html>"""


def chrome(i, n=5):
    return f'<div class="brand">{LOGO.format(s=38)}티커맵</div><div class="pg">{i}/{n}</div>'


# ---------------------------------------------------------------- 1) 마이크로소프트: 서프라이즈인데 하락
def msft():
    L4 = [x for x in MS["er"]["hist"] if x[2] is not None][-4:]
    beat = sum(1 for x in L4 if x[2] > 0)
    dn = sum(1 for x in L4 if x[2] > 0 and x[1] < 0)
    s1 = (f'<div class="eyebrow">마이크로소프트</div>'
          f'<div class="h" style="margin-top:60px">{beat}번 연속<br>예상을 넘었다.</div>'
          f'<div class="h o" style="margin-top:70px">그런데 주가는<br>{dn}번 떨어졌다.</div>'
          f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:80px">'
          + "".join(f'<div style="text-align:center;border-radius:20px;padding:20px 0;background:{K["or_"] if ex > 0 else K["bl"]};color:#fff;font-size:30px;font-weight:800">예상 ✓<div style="font-size:64px;font-weight:900;line-height:1.1">{"▲" if ex > 0 else "▼"}</div></div>' for d, ex, s_ in L4)
          + '</div>' + chrome(1))
    mx = max(abs(x[1]) for x in L4)
    cols = ""
    for d, ex, s in L4:
        c = K["or_"] if ex > 0 else K["bl"]
        h = abs(ex) / mx * 300
        up = f'<div style="height:330px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center">' + (f'<b style="font-size:46px;color:{c}">{ex * 100:+.0f}%</b><div style="width:100%;height:{h:.0f}px;background:{c};border-radius:14px 14px 0 0;margin-top:10px"></div>' if ex > 0 else "") + "</div>"
        dw = f'<div style="height:330px;display:flex;flex-direction:column;align-items:center">' + (f'<div style="width:100%;height:{h:.0f}px;background:{c};border-radius:0 0 14px 14px"></div><b style="font-size:46px;color:{c};margin-top:10px">{ex * 100:+.0f}%</b>' if ex < 0 else "") + "</div>"
        cols += (f'<div><div style="text-align:center;font-size:28px;font-weight:800;background:{K["ink"]};color:{K["cream"]};border-radius:12px;padding:10px 0">예상 넘음 ✓</div>'
                 f'<div style="margin-top:24px">{up}<div style="height:3px;background:{K["ink"]}"></div>{dw}</div>'
                 f'<div style="text-align:center;font-size:28px;font-weight:700;opacity:.6;margin-top:6px">{d[2:4]}년 {int(d[5:7])}월</div></div>')
    s2 = (f'<div class="m">성적표는 매번 합격,<br>주가 반응은 제각각</div>'
          f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:26px;margin-top:70px">{cols}</div>'
          f'<div class="tiny" style="margin-top:22px">발표 다음 거래일 주가, S&P 500 대비</div>' + chrome(2))
    s3 = (f'<div class="m" style="margin-top:40px">시장은<br>"예상보다 잘했나"보다</div>'
          f'<div class="m o" style="margin-top:30px">"기대보다 잘했나"를<br>본다</div>'
          f'<div class="s" style="margin-top:80px">예상치는 애널리스트가 공개한 숫자.<br>기대는 이미 주가에 들어가 있는 숫자.<br>둘은 다를 때가 많아요.</div>' + chrome(3))
    avg = MS["er"]["avg"]
    s4 = (f'<div class="eyebrow">이번 주 목요일 새벽, 한국 시간</div>'
          f'<div class="m" style="margin-top:40px">마이크로소프트가<br>다시 성적표를 낸다</div>'
          f'<div style="margin-top:110px;font-size:40px;font-weight:800;opacity:.6">지난 8번, 발표 다음 날 평균</div>'
          f'<div style="font-size:260px;font-weight:900;letter-spacing:-0.06em;line-height:1" class="o">±{avg * 100:.1f}%</div>'
          f'<div class="s" style="margin-top:20px">오를지 내릴지가 아니라, 얼마나 크게 움직였는지예요.</div>' + chrome(4))
    s5 = (f'<div class="m">실적 발표 전에<br>이 세 가지만 보세요</div>'
          + "".join(f'<div style="display:flex;gap:28px;align-items:baseline;margin-top:{60 if i == 1 else 34}px"><b class="o" style="font-size:72px;font-weight:900">{i}</b>'
                    f'<div><div style="font-size:50px;font-weight:900">{a}</div><div style="font-size:30px;opacity:.6;font-weight:600;margin-top:6px">{b}</div></div></div>'
                    for i, (a, b) in enumerate([("지난 반응", "발표 다음 날 평소 얼마나 움직였나"), ("전망 변화", "최근 90일 애널리스트 전망이 올랐나 내렸나"), ("옵션 예상", "이번엔 시장이 얼마나 큰 변동을 걸었나")], 1))
          + f'<div style="margin-top:70px;background:{K["ink"]};color:{K["cream"]};border-radius:24px;padding:30px 36px;font-size:36px;font-weight:800">tickermap.kr — 종목마다 한 장에, 무료로</div>'
          f'<div class="tiny" style="margin-top:28px">기준일 {MS["asof"]} 종가 · 출처: SEC 8-K 접수 시각, 컨센서스·주가 시세, 티커맵 계산 · 반응 = 장 후 발표는 다음 거래일 수익률 − S&P 500(SPY) 수익률<br>정보 제공용이며 투자 권유가 아닙니다.</div>'
          + chrome(5))
    return {"01": (s1, None, None), "02": (s2, None, None), "03": (s3, K["dark"], K["cream"]), "04": (s4, None, None), "05": (s5, None, None)}


# ---------------------------------------------------------------- 2) 고배당의 함정
def dots(n, on, color, cols=10, size=58, gap=16):
    return (f'<div style="display:grid;grid-template-columns:repeat({cols},{size}px);gap:{gap}px">'
            + "".join(f'<div style="width:{size}px;height:{size}px;border-radius:50%;background:{color if i < on else K["line"]}"></div>' for i in range(n)) + "</div>")


def div():
    A, B = SP["cut_1y_by_yield_large"], SP["cut_1y_by_yield_large_and_ret1y_le_-20pct"]
    hi, lo, hib = A[">=6%"], A["<2%"], B[">=6%"]
    s1 = (f'<div class="eyebrow">배당 6% 넘는 미국 주식</div>'
          f'<div class="h" style="margin-top:60px"><span class="o">4곳 중 1곳</span>은<br>1년 안에<br>배당을 깎았다</div>'
          f'<div style="margin-top:90px">{dots(4, 1, K["or_"], cols=4, size=150, gap=34)}</div>' + chrome(1))
    s2 = (f'<div class="m">배당이 낮은 회사는<br><span class="b">100곳 중 {lo * 100:.0f}곳</span></div>'
          f'<div style="margin-top:36px">{dots(100, round(lo * 100), K["bl"], cols=20, size=36, gap=11)}</div>'
          f'<div class="m" style="margin-top:80px">6% 넘으면<br><span class="o">100곳 중 {hi * 100:.0f}곳</span></div>'
          f'<div style="margin-top:36px">{dots(100, round(hi * 100), K["or_"], cols=20, size=36, gap=11)}</div>' + chrome(2))
    s3 = (f'<div class="m">주가까지 1년 새<br>크게 빠졌다면?</div>'
          f'<div style="font-size:300px;font-weight:900;letter-spacing:-0.06em;line-height:1;margin-top:70px" class="o">10곳 중<br>{hib * 10:.0f}곳</div>'
          f'<div class="s" style="margin-top:40px">배당 6% 이상 + 지난 1년 시장보다 20% 넘게 부진한 회사의 과거 삭감 비율 {hib * 100:.0f}%</div>' + chrome(3))
    s4 = (f'<div class="m" style="margin-top:40px">배당이 높은 이유가</div>'
          f'<div class="m o" style="margin-top:20px">"주가가 빠져서"<br>일 수 있다</div>'
          f'<div style="margin-top:90px;font-size:58px;font-weight:900;line-height:1.5">배당수익률 = 배당 ÷ <span class="o">주가</span></div>'
          f'<div class="s" style="margin-top:30px">배당은 그대로인데 주가가 반토막 나면<br>배당수익률은 두 배가 돼요.</div>' + chrome(4))
    s5 = (f'<div class="m">내 배당주,<br>이 두 가지만 보세요</div>'
          + "".join(f'<div style="display:flex;gap:28px;align-items:baseline;margin-top:{60 if i == 1 else 34}px"><b class="o" style="font-size:72px;font-weight:900">{i}</b>'
                    f'<div><div style="font-size:50px;font-weight:900">{a}</div><div style="font-size:30px;opacity:.6;font-weight:600;margin-top:6px">{b}</div></div></div>'
                    for i, (a, b) in enumerate([("배당수익률 구간", "2% 미만 · 2~4% · 4~6% · 6% 이상"), ("지난 1년 주가", "시장보다 20% 넘게 빠졌나")], 1))
          + f'<div style="margin-top:80px;background:{K["ink"]};color:{K["cream"]};border-radius:24px;padding:30px 36px;font-size:36px;font-weight:800">tickermap.kr — 종목마다 배당 점검, 무료로</div>'
          f'<div class="tiny" style="margin-top:28px">기준: 시가총액 20억 달러 이상 미국 분기 배당 회사의 과거 기록(2006년~), 1년 안 배당 삭감·중단 비율. 삭감 = 직전보다 0.5% 넘게 감소, 특별배당 제외. 과거 집단 통계이며 개별 회사의 앞날을 뜻하지 않아요. 출처: SEC 공시, 배당·주가 시세, 티커맵 계산 · 기준일 2026-10-23<br>정보 제공용이며 투자 권유가 아닙니다.</div>'
          + chrome(5))
    return {"01": (s1, None, None), "02": (s2, None, None), "03": (s3, K["dark"], K["cream"]), "04": (s4, None, None), "05": (s5, None, None)}


def main():
    from playwright.sync_api import sync_playwright
    font = base64.b64encode((ASSETS / "PretendardVariable.woff2").read_bytes()).decode()
    txt = lambda s: re.sub(r"<[^>]+>", "", s)
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": W, "height": HH})
        for name, S in [("v2ms", msft()), ("v2dv", div())]:
            allt = " ".join(txt(v[0]) for v in S.values())
            print(name, "금지:", [w for w in H["banned"] if w in allt] or "없음",
                  "| 마지막 장 누락:", [w for w in H["required_last_slide"] if w not in txt(S["05"][0])] or "없음")
            for k, (body, bg, ink) in S.items():
                html_ = page(body, font, bg, ink)
                if bg == K["dark"]:
                    html_ = html_.replace(".o{{", ".o{{")
                pg.set_content(html_)
                pg.wait_for_timeout(150)
                pg.screenshot(path=str(OUT / f"{name}_{k}.png"))
        br.close()


if __name__ == "__main__":
    main()
