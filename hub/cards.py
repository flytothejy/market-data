"""주간 홍보 카드 — 티커맵을 SNS용 이미지로 (인스타·스레드 캐러셀 5장 + X·블로그용 가로 1장 + 본문)

  python -m hub run cards                 이번 주 렌즈(주마다 돌아가며)로 생성
  CARDS_LENS=rev python -m hub run cards  렌즈 지정 (eps · rev · insider)

결과: data/hub/site/cards/<가격 기준일>/  01.png … 05.png (1080×1350), wide.png (1600×900), caption.txt, meta.json
      data/hub/site/cards/latest.json (사이트에서 최신 카드 찾기용), 텔레그램으로 사진 묶음 + 본문 전송
렌더링: Playwright(Chromium) + 저장소에 들어 있는 Pretendard 글꼴(OFL)
"""
import base64, html, json, math, os, datetime as dt
from pathlib import Path

import requests

from .core import DATA, Run, log

SITE = DATA / "site" / "api" / "v1"
OUT = DATA / "site" / "cards"
ASSETS = Path(__file__).parent / "cards_assets"
SITE_URL = os.environ.get("SITE_URL", "https://flytothejy.github.io/market-data").rstrip("/")
KEEP_WEEKS = 12
MIN_CAP = 1e10

XW = {"r1m": ("1개월", 0.3, 2)}            # 가로축: 최근 1개월 주가 (트레일 점의 2번째 값)
LENS = {
    "eps": dict(max=0.3, rank_max=1.0, trail="eps@3m", metric="EPS 전망", unit="pct",
                y=lambda r: r.get("c_chg90") if r.get("c_chg90") is not None and (r.get("c_n") or 0) >= 3 else None,
                kicker="이익 전망 × 주가", h1=("주가는 빠졌는데", "이익 전망은 올랐다"),
                tl="이익 전망은 오르는데\n주가는 빠진 종목", br="주가는 오르는데\n이익 전망은 꺾인 종목",
                tl_short="전망↑ 주가↓", br_short="주가↑ 전망↓", up="내년 EPS 전망 상향", dn="전망 하향",
                note="EPS 전망 = 애널리스트들의 내년 주당순이익 전망이 90일 전보다 얼마나 바뀌었나"),
    "rev": dict(max=0.3, rank_max=0.5, trail="rev@1y", metric="매출 가속", unit="pp",
                y=lambda r: (r["rev_qg"] - r["rev_g"]) if r.get("rev_qg") is not None and r.get("rev_g") is not None else None,
                kicker="매출 성장 × 주가", h1=("주가는 빠졌는데", "매출 성장은 빨라졌다"),
                tl="매출 성장은 빨라지는데\n주가는 빠진 종목", br="주가는 오르는데\n매출 성장은 둔화된 종목",
                tl_short="매출 가속 · 주가↓", br_short="주가↑ · 매출 둔화", up="매출 성장 가속", dn="둔화",
                note="매출 가속 = 최근 분기 매출 성장률 − 최근 4개 분기 성장률 (SEC 재무제표)"),
    "insider": dict(max=1, raw=True, trail="insider@1y", rank_ok=lambda r: abs((r.get("ib") or 0) - (r.get("is") or 0)) >= 1e5, metric="내부자 순매수", unit="usd",
                    y=lambda r: _ins(r), kicker="내부자 거래 × 주가", h1=("주가는 빠졌는데", "임원들은 샀다"),
                    tl="내부자는 사는데\n주가는 빠진 종목", br="주가는 오르는데\n내부자는 판 종목",
                    tl_short="내부자 매수 · 주가↓", br_short="주가↑ · 내부자 매도", up="내부자 순매수", dn="순매도",
                    note="내부자 = 최근 90일 임원·이사의 장내 매수 − 매도 금액 (SEC Form 4)"),
}
ROTATE = ["eps", "rev", "insider"]

C = dict(bg="#121210", panel="#1b1b18", line="#2e2d29", ink="#f4f3ee", mut="#a6a59e", faint="#6f6e68",
         up="#ff7a33", dn="#4d8dff", up_t="rgba(255,122,51,.10)", dn_t="rgba(77,141,255,.10)")


def _ins(r):
    n = (r.get("ib") or 0) - (r.get("is") or 0)
    return math.copysign(max(0.05, min(1, (math.log10(abs(n)) - 4) / 4.5)), n) if n else None


def clamp(v, a, b):
    return max(a, min(b, v))


def fmt_pct(v, d=0):
    return ("+" if v > 0 else "") + f"{v * 100:.{d}f}%"


def fmt_signal(L, r, y):
    if L["unit"] == "pct":
        return "전망 " + fmt_pct(y, 1 if abs(y) < 0.1 else 0)
    if L["unit"] == "pp":
        return "매출 " + ("+" if y > 0 else "") + f"{y * 100:.1f}%p"
    n = (r.get("ib") or 0) - (r.get("is") or 0)
    a = abs(n)
    s = f"{a / 1e8:.1f}억 달러" if a >= 1e8 else f"{a / 1e4:,.0f}만 달러" if a >= 1e4 else f"{a:,.0f}달러"
    return ("매수 " if n > 0 else "매도 ") + s


def points(rows, L, xw="r1m"):
    xm = XW[xw][1]
    out = []
    for r in rows:
        x, y = r.get(xw), L["y"](r)
        if x is None or y is None or (r.get("mcap") or 0) < MIN_CAP:
            continue
        yC = y if L.get("raw") else clamp(y / L["max"], -1, 1)
        xN = clamp(x / xm, -1, 1)
        q = "tl" if yC > 0.03 and x < -0.003 else "br" if yC < -0.03 and x > 0.003 else "tr" if yC >= 0 and x >= 0 else "bl"
        score = min(abs(xN), abs(yC)) + 0.3 * (abs(xN) + abs(yC))
        out.append(dict(t=r["t"], ko=r.get("ko") or "", n=r.get("n") or "", mcap=r.get("mcap") or 0, x=x, y=y, xN=xN, yC=yC, q=q, score=score, r=r,
                        xu=x / xm, yu=y if L.get("raw") else y / L["max"]))
    return out


def top(P, q, L, n=5):
    """구역별 상위 — 지도 끝에 붙은(값이 너무 큰) 종목은 기저 효과(적자→흑자 등)인 경우가 많아 순위에서는 뺌"""
    lim, ok = L.get("rank_max"), L.get("rank_ok") or (lambda r: True)
    c = [p for p in P if p["q"] == q and abs(p["yC"]) > 0.06 and abs(p["xN"]) > 0.06 and (lim is None or abs(p["y"]) <= lim) and ok(p["r"])]
    return sorted(c, key=lambda p: (-round(p["score"], 2), -p["mcap"]))[:n]


# ---------------------------------------------------------------- 그림 조각 (SVG)
LOGO = ('<svg viewBox="0 0 28 28" width="{s}" height="{s}"><circle cx="7.8" cy="7.8" r="6.8" fill="#d65014"/><circle cx="20.6" cy="5.4" r="4.4" fill="#2463c4"/>'
        '<circle cx="21.8" cy="13.2" r="2.4" fill="#d9d6cc"/><circle cx="6.1" cy="20.9" r="4.1" fill="#7ea3dc"/><circle cx="18.2" cy="20.2" r="4.8" fill="#eba27e"/>'
        '<circle cx="12.9" cy="15.3" r="1.5" fill="#d9d6cc"/></svg>')


def map_svg(P, L, W, H, hot=(), labels=True, pad=(34, 26, 40, 30), trail=None, quad_labels=True, fs=1.0, dom=None):
    """티커맵 한 장: 왼쪽 위(주황)·오른쪽 아래(파랑)가 어긋난 구역"""
    pl, pr, pt, pb = pad
    iw, ih = W - pl - pr, H - pt - pb
    x0, x1, y0, y1 = dom or (-1.04, 1.04, -1.04, 1.04)
    kx, ky = ("xu", "yu") if dom else ("xN", "yC")
    sx = lambda v: pl + (v - x0) / (x1 - x0) * iw
    sy = lambda v: pt + (y1 - v) / (y1 - y0) * ih
    g = [f'<rect x="{sx(x0)}" y="{sy(y1)}" width="{max(0, sx(min(0, x1)) - sx(x0))}" height="{max(0, sy(max(0, y0)) - sy(y1))}" fill="{C["up_t"]}"/>' if x0 < 0 and y1 > 0 else "",
         f'<rect x="{sx(max(0, x0))}" y="{sy(min(0, y1))}" width="{max(0, sx(x1) - sx(max(0, x0)))}" height="{max(0, sy(y0) - sy(min(0, y1)))}" fill="{C["dn_t"]}"/>' if x1 > 0 and y0 < 0 else "",
         f'<line x1="{sx(0)}" x2="{sx(0)}" y1="{pt}" y2="{pt + ih}" stroke="{C["line"]}" stroke-width="2"/>' if x0 < 0 < x1 else "",
         f'<line x1="{pl}" x2="{pl + iw}" y1="{sy(0)}" y2="{sy(0)}" stroke="{C["line"]}" stroke-width="2"/>' if y0 < 0 < y1 else ""]
    if quad_labels:
        g.append(f'<text x="{pl}" y="{pt - 14}" font-size="{25 * fs}" font-weight="800" fill="{C["up"]}">◤ {html.escape(L["tl_short"])}</text>')
        g.append(f'<text x="{pl + iw}" y="{pt - 14}" font-size="{25 * fs}" font-weight="800" fill="{C["dn"]}" text-anchor="end">{html.escape(L["br_short"])} ◢</text>')
    g.append(f'<text x="{pl + iw / 2}" y="{H - 6}" font-size="{19 * fs}" fill="{C["mut"]}" text-anchor="middle">← 최근 1개월 주가 하락 · 상승 →</text>')
    g.append(f'<text x="{pl - 10}" y="{pt + ih / 2}" font-size="{19 * fs}" fill="{C["mut"]}" text-anchor="middle" transform="rotate(-90 {pl - 10} {pt + ih / 2})">← {html.escape(L["dn"])} · {html.escape(L["up"])} →</text>')
    maxM = max([p["mcap"] for p in P] or [1])
    hotset = {p["t"] for p in hot}
    dots, labs, want = [], [], []
    for p in sorted(P, key=lambda p: -p["mcap"]):
        rad = (4 + math.sqrt(p["mcap"] / maxM) * 44 * fs) if not trail else (3 + math.sqrt(p["mcap"] / maxM) * 26 * fs)
        if not (x0 <= p[kx] <= x1 and y0 <= p[ky] <= y1):
            continue
        cx, cy = sx(p[kx]), sy(p[ky])
        col = C["up"] if p["q"] == "tl" else C["dn"] if p["q"] == "br" else C["faint"]
        op = (0.78 if p["q"] in ("tl", "br") else 0.30) * (0.35 if trail else 1)
        if p["t"] in hotset:
            op = 0.95
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" fill="{col}" fill-opacity="{op}" stroke="{col}" stroke-opacity=".9" stroke-width="1.2"/>')
        if labels and p["t"] in hotset:
            want.append((p, cx, cy, rad))
    # 이름표 겹침 피하기: 오른쪽 → 왼쪽 → 위 → 아래 → 더 멀리 순서로 빈자리 찾기
    fsz = 24 * fs
    boxes = []
    for p, cx, cy, rad in sorted(want, key=lambda w: -w[0]["score"]):
        tw, th = len(p["t"]) * fsz * 0.66, fsz
        for dx, dy, anc in [(rad + 6, 0, "s"), (-rad - 6, 0, "e"), (0, -rad - 8, "m"), (0, rad + th + 2, "m"),
                            (rad + 6, -th, "s"), (rad + 6, th, "s"), (-rad - 6, -th, "e"), (-rad - 6, th, "e"), (0, -rad - th - 10, "m"), (0, rad + 2 * th + 6, "m")]:
            x0 = cx + dx - (tw if anc == "e" else tw / 2 if anc == "m" else 0)
            y0 = cy + dy - th * 0.75
            bx = (x0 - 3, y0 - 3, x0 + tw + 3, y0 + th + 3)
            if bx[0] < 2 or bx[2] > W - 2 or bx[1] < 2 or bx[3] > H - 2:
                continue
            if all(bx[2] < o[0] or bx[0] > o[2] or bx[3] < o[1] or bx[1] > o[3] for o in boxes):
                boxes.append(bx)
                ta = {"s": "start", "e": "end", "m": "middle"}[anc]
                labs.append(f'<text x="{cx + dx:.1f}" y="{cy + dy + th * 0.33:.1f}" font-size="{fsz}" font-weight="800" text-anchor="{ta}" fill="{C["ink"]}" paint-order="stroke" stroke="{C["bg"]}" stroke-width="6" stroke-linejoin="round">{html.escape(p["t"])}</text>')
                break
    tr = ""
    if trail:
        pts = [(sx(x), sy(y), d) for x, y, d in trail]
        n = len(pts)
        for i in range(n - 1):
            a, b = pts[i], pts[i + 1]
            o = 0.25 + 0.75 * (i + 1) / (n - 1)
            tr += f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{C["ink"]}" stroke-opacity="{o:.2f}" stroke-width="5" stroke-linecap="round"/>'
        for i, (x, y, d) in enumerate(pts):
            last = i == n - 1
            o = 0.3 + 0.7 * i / max(1, n - 1)
            r = 13 if last else 9
            tr += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{C["up"] if last else C["ink"]}" fill-opacity="{1 if last else o:.2f}" stroke="{C["bg"]}" stroke-width="3"/>'
            lab = "지금" if last else f'{int(d[5:7])}/{int(d[8:10])}'
            tr += f'<text x="{x + (18 if last else 14):.1f}" y="{y - 12:.1f}" font-size="{26 if last else 22}" font-weight="{900 if last else 700}" fill="{C["ink"]}" fill-opacity="{1 if last else max(o, .55):.2f}" paint-order="stroke" stroke="{C["bg"]}" stroke-width="6">{lab}</text>'
    return f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(g)}{"".join(dots)}{tr}{"".join(labs)}</svg>'


def bar(v, vmax, color, w=150):
    """가운데 기준 막대 (음수는 왼쪽)"""
    f = clamp(abs(v) / vmax, 0.04, 1) * (w / 2)
    x = w / 2 - f if v < 0 else w / 2
    return f'<svg width="{w}" height="14"><rect x="0" y="6" width="{w}" height="2" fill="{C["line"]}"/><rect x="{x:.1f}" y="1" width="{f:.1f}" height="12" rx="3" fill="{color}"/></svg>'


# ---------------------------------------------------------------- 페이지 (HTML)
def page(body, W, H, font):
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
@font-face{{font-family:P;src:url(data:font/woff2;base64,{font}) format('woff2');font-weight:45 920}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{W}px;height:{H}px;background:{C['bg']};color:{C['ink']};font-family:P,sans-serif;letter-spacing:-0.02em;overflow:hidden}}
.wrap{{position:relative;width:{W}px;height:{H}px;padding:64px 72px}}
.top{{display:flex;align-items:center;justify-content:space-between;font-size:26px;color:{C['mut']};font-weight:600}}
.brand{{display:flex;align-items:center;gap:12px;color:{C['ink']};font-weight:800;font-size:30px}}
.kick{{margin-top:44px;font-size:30px;font-weight:800;color:{C['up']};letter-spacing:0}}
h1{{font-size:88px;line-height:1.08;font-weight:900;letter-spacing:-0.045em;margin-top:14px}}
h1 em{{font-style:normal;color:{C['up']}}}
h2{{font-size:64px;line-height:1.12;font-weight:900;letter-spacing:-0.04em;white-space:pre-line}}
.foot{{position:absolute;left:72px;right:72px;bottom:52px;display:flex;justify-content:space-between;align-items:center;font-size:23px;color:{C['faint']}}}
.next{{color:{C['ink']};font-weight:700}}
.row{{display:grid;grid-template-columns:70px 1fr 360px;align-items:center;gap:18px;padding:26px 0;border-top:2px solid {C['line']}}}
.row:first-of-type{{border-top:0}}
.rk{{font-size:54px;font-weight:900;color:{C['faint']}}}
.tk{{font-size:52px;font-weight:900;letter-spacing:-0.03em}}
.nm{{font-size:26px;color:{C['mut']};margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mx{{display:grid;white-space:nowrap;grid-template-columns:auto 150px;gap:6px 14px;align-items:center;justify-items:end;font-size:25px;font-weight:700}}
.mx small{{font-size:19px;color:{C['mut']};font-weight:600;justify-self:start;grid-column:1/3}}
.chip{{display:inline-flex;align-items:center;gap:10px;font-size:26px;font-weight:800;padding:10px 18px;border-radius:999px}}
</style></head><body><div class="wrap">{body}</div></body></html>"""


def top_bar(asof, wk):
    return f'<div class="top"><div class="brand">{LOGO.format(s=40)}티커맵</div><div>{wk} · {asof[5:7].lstrip("0")}/{asof[8:10].lstrip("0")} 종가 기준</div></div>'


def list_slide(L, items, q, asof, wk, idx, total):
    col = C["up"] if q == "tl" else C["dn"]
    title = L[q]
    vx = max([abs(p["x"]) for p in items] or [0.1])
    vy = max([abs(p["y"]) for p in items] or [0.1])
    rows = ""
    for i, p in enumerate(items, 1):
        sig = fmt_signal(L, p["r"], p["y"])
        rows += (f'<div class="row"><div class="rk">{i}</div><div><div class="tk">{html.escape(p["t"])}</div><div class="nm">{html.escape(p["ko"] or p["n"])}</div></div>'
                 f'<div class="mx"><span style="color:{C["dn"] if p["x"] < 0 else C["up"]}">주가 {fmt_pct(p["x"])}</span>{bar(p["x"], vx, C["dn"] if p["x"] < 0 else C["up"])}'
                 f'<span style="color:{C["up"] if p["y"] > 0 else C["dn"]}">{html.escape(sig)}</span>{bar(p["y"], vy, C["up"] if p["y"] > 0 else C["dn"])}</div></div>')
    if not items:
        rows = f'<div style="font-size:34px;color:{C["mut"]};margin-top:80px">이번 주에는 해당 종목이 없어요.</div>'
    chip_bg = C["up_t"] if q == "tl" else C["dn_t"]
    return (top_bar(asof, wk) +
            f'<div style="margin-top:46px"><span class="chip" style="background:{chip_bg};color:{col}"><svg width="16" height="16"><circle cx="8" cy="8" r="8" fill="{col}"/></svg>'
            f'{"왼쪽 위" if q == "tl" else "오른쪽 아래"} 구역</span></div>'
            f'<h2 style="margin-top:22px">{html.escape(title)}</h2>'
            f'<div style="margin-top:34px">{rows}</div>'
            f'<div class="foot"><span>주가 = 최근 1개월 · {html.escape(L["metric"])} · 시총 100억 달러 이상</span><span class="next">{idx}/{total}</span></div>')


def run(limit=0, **_):
    R = Run("cards")
    p = SITE / "free" / "universe.json"
    if os.environ.get("R2_BUCKET"):                      # 지난 카드(정리용)와, 단독 실행이면 화면 데이터도 R2에서 받음
        from . import sync
        try:
            sync.pull(only=["site/cards/"] + ([] if p.exists() else ["site/api/v1/free/universe.json", "site/api/v1/free/stock/"]))
        except Exception as e:
            R.warning(f"R2에서 받기 실패: {e}")
    if not p.exists():
        R.warning("치명: universe.json 없음")
        return R.done(ok=False)
    U = json.loads(p.read_text(encoding="utf-8"))
    rows = [r for r in U["rows"] if r.get("k") == "stock"]
    asof = str(U["asof"])[:10]
    d = dt.date.fromisoformat(asof)
    lens = os.environ.get("CARDS_LENS") or ROTATE[d.isocalendar()[1] % len(ROTATE)]
    L = LENS[lens]
    wk = f"{d.month}월 {(d.day - 1) // 7 + 1}주"
    P = points(rows, L)
    TL, BR = top(P, "tl", L), top(P, "br", L)
    R.set(lens=lens, asof=asof, stocks=len(P), tl=" ".join(p["t"] for p in TL), br=" ".join(p["t"] for p in BR))
    log(f"카드: 렌즈 {lens}, 종목 {len(P)}, 왼쪽 위 {[p['t'] for p in TL]}, 오른쪽 아래 {[p['t'] for p in BR]}")
    n_tl = sum(1 for p in P if p["q"] == "tl" and abs(p["yC"]) > 0.06 and abs(p["xN"]) > 0.06)

    # 트레일: 왼쪽 위 1등 (렌즈에 트레일이 없으면 생략)
    trail, tstock = None, None
    for cand in (TL if L["trail"] else []):
        sp = SITE / "free" / "stock" / f"{cand['t']}.json"
        if not sp.exists():
            continue
        tr = (json.loads(sp.read_text(encoding="utf-8")).get("trail") or {}).get(L["trail"]) or []
        xm, xi = XW["r1m"][1], XW["r1m"][2]
        pts = [(q[xi] / xm, q[5] if L.get("raw") else q[5] / L["max"], q[0]) for q in tr if q[xi] is not None and q[5] is not None]
        if pts and pts[-1][2] >= asof:
            pts = pts[:-1]
        pts.append((cand["xu"], cand["yu"], asof))
        if len(pts) >= 4:
            trail, tstock = pts, cand
            break

    font = base64.b64encode((ASSETS / "PretendardVariable.woff2").read_bytes()).decode()
    slides = []
    total = 5 if trail else 4
    hot = TL[:5] + BR[:5]
    h1a, h1b = L["h1"]
    s1 = (top_bar(asof, wk) + f'<div class="kick">이번 주 어긋난 종목 · {html.escape(L["kicker"])}</div>'
          f'<h1>{html.escape(h1a)}<br><em>{html.escape(h1b)}</em></h1>'
          f'<div style="margin-top:30px;margin-left:-20px">{map_svg(P, L, 976, 800, hot=hot)}</div>'
          f'<div class="foot"><span>점 하나 = 미국 대형주 1개 (크기 = 시가총액) · {len(P)}종목</span><span class="next">넘겨서 종목 보기 →</span></div>')
    slides.append((s1, 1080, 1350))
    slides.append((list_slide(L, TL, "tl", asof, wk, 2, total), 1080, 1350))
    slides.append((list_slide(L, BR, "br", asof, wk, 3, total), 1080, 1350))
    if trail:
        xs, ys = [q[0] for q in trail] + [0], [q[1] for q in trail] + [0]
        mx_, my_ = max(0.25, (max(xs) - min(xs)) * 0.18), max(0.25, (max(ys) - min(ys)) * 0.18)
        tdom = (min(xs) - mx_, max(xs) + mx_, min(ys) - my_, max(ys) + my_)
        name = tstock["ko"] or tstock["n"]
        s4 = (top_bar(asof, wk) + f'<div class="kick">티커 트레일 · 지나온 길</div>'
              f'<h2 style="margin-top:14px">{html.escape(tstock["t"])}{(" " + html.escape(name)) if name and len(name) <= 10 else ""},<br>지난 {"3개월" if L["trail"].endswith("3m") else "1년"} 이렇게 움직였어요</h2>'
              f'<div style="margin-top:26px;margin-left:-20px">{map_svg(P, L, 976, 820, hot=[], labels=False, trail=trail, dom=tdom)}</div>'
              f'<div class="foot"><span>흐린 점 → 진한 점 순서 · 각 시점의 1개월 주가 × {html.escape(L["metric"])}</span><span class="next">4/{total}</span></div>')
        slides.append((s4, 1080, 1350))
    host = SITE_URL.split("://", 1)[-1]
    s5 = (top_bar(asof, wk) +
          f'<div style="position:absolute;left:72px;right:72px;top:300px">'
          f'<div style="display:flex;justify-content:center;margin-bottom:56px">{LOGO.format(s=150)}</div>'
          f'<h1 style="text-align:center;font-size:96px">내 종목은<br><em>지도 어디쯤?</em></h1>'
          f'<div style="text-align:center;font-size:34px;color:{C["mut"]};margin-top:34px;line-height:1.5">미국 주식 1,000여 개의 위치를 매일 아침 갱신<br>이익 전망 · 매출 · 유명 투자자 · 내부자 · 공매도</div>'
          f'<div style="text-align:center;margin-top:56px"><span class="chip" style="background:{C["ink"]};color:{C["bg"]};font-size:34px;padding:20px 34px">{html.escape(host)}</span></div></div>'
          f'<div class="foot" style="display:block;text-align:center;line-height:1.6;font-size:21px">투자 권유가 아닌 정보 제공 목적입니다. 데이터: SEC · FINRA · Yahoo Finance<br>{html.escape(L["note"])}</div>')
    slides.append((s5, 1080, 1350))
    # X·블로그용 가로 1장
    side = ""
    for q, items in (("tl", TL[:3]), ("br", BR[:3])):
        col = C["up"] if q == "tl" else C["dn"]
        side += f'<div style="font-size:28px;font-weight:900;color:{col};margin:{0 if q == "tl" else 34}px 0 10px;white-space:pre-line">{html.escape(L[q].replace(chr(10), " "))}</div>'
        for p in items:
            side += (f'<div style="display:flex;justify-content:space-between;align-items:baseline;padding:12px 0;border-top:2px solid {C["line"]}">'
                     f'<span><b style="font-size:38px;font-weight:900">{html.escape(p["t"])}</b> <span style="font-size:22px;color:{C["mut"]}">{html.escape((p["ko"] or p["n"])[:12])}</span></span>'
                     f'<span style="font-size:23px;font-weight:700"><span style="color:{C["dn"] if p["x"] < 0 else C["up"]}">주가 {fmt_pct(p["x"])}</span> · '
                     f'<span style="color:{C["up"] if p["y"] > 0 else C["dn"]}">{html.escape(fmt_signal(L, p["r"], p["y"]))}</span></span></div>')
    wide = (f'<div style="display:grid;grid-template-columns:820px 1fr;gap:40px;height:100%">'
            f'<div style="margin:-20px 0 0 -30px">{map_svg(P, L, 840, 780, hot=hot, fs=0.9)}</div>'
            f'<div style="display:flex;flex-direction:column"><div class="brand" style="font-size:30px">{LOGO.format(s=40)}티커맵 <span style="color:{C["mut"]};font-weight:600;font-size:24px;margin-left:8px">{wk} · {asof[5:].replace("-", "/")} 종가</span></div>'
            f'<div style="font-size:54px;line-height:1.1;font-weight:900;letter-spacing:-0.04em;margin:26px 0 30px">{html.escape(h1a)}<br><span style="color:{C["up"]}">{html.escape(h1b)}</span></div>'
            f'{side}<div style="margin-top:auto;font-size:19px;color:{C["faint"]}">{html.escape(host)} · 투자 권유 아님</div></div></div>')
    slides.append((wide, 1600, 900))

    out = OUT / asof
    out.mkdir(parents=True, exist_ok=True)
    files = []
    from playwright.sync_api import sync_playwright
    tmp = out / "_tmp.html"
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(device_scale_factor=1)
        for i, (body, W, H) in enumerate(slides, 1):
            name = "wide.png" if W == 1600 else f"{i:02d}.png"
            tmp.write_text(page(body, W, H, font), encoding="utf-8")
            pg.set_viewport_size({"width": W, "height": H})
            pg.goto(tmp.as_uri())
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(out / name))
            files.append(out / name)
        b.close()
    tmp.unlink(missing_ok=True)

    # 본문 (인스타·스레드·블로그 공통, X는 첫 줄 + 링크만 써도 됨)
    def line(p):
        return f"{p['t']}{'(' + p['ko'] + ')' if p['ko'] else ''} 주가 {fmt_pct(p['x'])} · {fmt_signal(L, p['r'], p['y'])}"
    url = f"{SITE_URL}/hub/matrix.html?lens={lens}"
    cap = (f"[티커맵 {wk}] {h1a} {h1b} ({asof[5:].replace('-', '/')} 종가 기준)\n\n"
           f"🟧 {L['tl'].replace(chr(10), ' ')}\n" + "\n".join(f"{i}. {line(p)}" for i, p in enumerate(TL, 1)) +
           f"\n\n🟦 {L['br'].replace(chr(10), ' ')}\n" + "\n".join(f"{i}. {line(p)}" for i, p in enumerate(BR, 1)) +
           f"\n\n시총 100억 달러 이상 미국 주식 {len(P)}개 중 왼쪽 위 구역 {n_tl}개.\n{L['note']}\n"
           f"전체 지도: {url}\n\n※ 투자 권유가 아닌 정보 제공 목적입니다.\n"
           "#미국주식 #해외주식 #주식공부 #티커맵 #" + {"eps": "실적전망", "rev": "매출성장", "insider": "내부자거래"}[lens])
    (out / "caption.txt").write_text(cap, encoding="utf-8")
    meta = {"asof": asof, "lens": lens, "week": wk, "files": [f.name for f in files], "caption": "caption.txt",
            "tl": [p["t"] for p in TL], "br": [p["t"] for p in BR]}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps({**meta, "dir": asof}, ensure_ascii=False), encoding="utf-8")
    # 오래된 카드 정리
    dirs = sorted(x for x in OUT.iterdir() if x.is_dir())
    for old in dirs[:-KEEP_WEEKS]:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
    R.set(files=len(files), dir=str(out.relative_to(DATA)))
    _telegram(files, cap, R)
    return R.done()


def _telegram(files, cap, R):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        car = [f for f in files if f.name != "wide.png"]
        media = [{"type": "photo", "media": f"attach://f{i}"} for i in range(len(car))]
        media[0]["caption"] = "티커맵 주간 카드 (인스타·스레드용 캐러셀)"
        fs = {f"f{i}": (f.name, f.read_bytes(), "image/png") for i, f in enumerate(car)}
        requests.post(f"https://api.telegram.org/bot{tok}/sendMediaGroup", data={"chat_id": chat, "media": json.dumps(media)}, files=fs, timeout=60)
        w = next((f for f in files if f.name == "wide.png"), None)
        if w:
            requests.post(f"https://api.telegram.org/bot{tok}/sendDocument", data={"chat_id": chat, "caption": "X·블로그용 가로 1장 (원본 화질)"},
                          files={"document": (w.name, w.read_bytes(), "image/png")}, timeout=60)
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": chat, "text": cap[:4000]}, timeout=20)
    except Exception as e:
        R.warning(f"텔레그램 전송 실패: {e}")
