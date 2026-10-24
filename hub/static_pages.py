"""검색엔진용 정적 페이지 — Pages 배포 때 실행 (python -m hub.static_pages _site)

화면은 자바스크립트로 그려서 검색엔진(특히 네이버)에는 빈 페이지로 보임 → 종목·ETF·투자자마다
제목·설명·핵심 숫자를 미리 넣은 HTML을 만든다. 열리면 기존 화면(stock.html·investors.html)이 그대로 덮어 그림.
  _site/hub/s/{티커}/index.html   종목·ETF  (stock.html + <base href="../../">)
  _site/hub/i/{CIK}/index.html    13F 투자자 (investors.html)
  _site/sitemap.xml, _site/robots.txt
사이트 주소는 환경변수 SITE_URL (도메인을 붙이면 여기만 바꿈)
"""
import csv, html, json, os, re, sys, datetime as dt
from pathlib import Path

SKEL = '<div class="wrap" id="app"><div class="skel" role="status" aria-label="불러오는 중"><i class="sk sk-h"></i><i class="sk sk-p"></i><div class="sk-grid"><i class="sk sk-c"></i><i class="sk sk-c"></i><i class="sk sk-c"></i></div><i class="sk sk-b"></i></div></div>'   # 화면 파일의 '불러오는 중' 자리 (web/*.html과 같아야 함)
SITE_URL = os.environ.get("SITE_URL", "https://flytothejy.github.io/market-data").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
SECTOR_KO = {"Technology": "기술", "Healthcare": "헬스케어", "Financial Services": "금융", "Consumer Cyclical": "경기소비재",
             "Consumer Defensive": "필수소비재", "Industrials": "산업재", "Energy": "에너지", "Utilities": "유틸리티",
             "Real Estate": "부동산", "Basic Materials": "소재", "Communication Services": "커뮤니케이션"}
e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def usd(v):
    if v is None:
        return "-"
    a, s = abs(v), "-" if v < 0 else ""
    if a >= 1e12:
        return f"{s}${a / 1e12:.2f}조"
    if a >= 1e8:
        return f"{s}${a / 1e8:,.0f}억"
    if a >= 1e4:
        return f"{s}${a / 1e4:,.0f}만"
    return f"{s}${a:,.2f}"


def pct(v, sign=True):
    if v is None:
        return "-"
    x = v * 100
    return f"{'+' if sign and x > 0 else ''}{x:.1f}%" if abs(x) < 10 else f"{'+' if sign and x > 0 else ''}{x:.0f}%"


def mmdd(d):
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else ""


OG_IMAGE = "hub/assets/app/og.png"
WD = "월화수목금토일"


def wday(d):
    try:
        return WD[dt.date.fromisoformat(d[:10]).weekday()]
    except Exception:
        return ""


def ld(*objs):
    """구조화 데이터(JSON-LD) — 검색엔진이 페이지 성격·질문과 답을 알아보게"""
    return "".join('<script type="application/ld+json">' + json.dumps(o, ensure_ascii=False).replace("</", "<\\/") + "</script>\n" for o in objs if o)


def crumbs(*items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": f"{SITE_URL}/{u}"} for i, (n, u) in enumerate(items)]}


def faq(qas):
    qas = [(q, a) for q, a in qas if q and a]
    if not qas:
        return None, ""
    obj = {"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qas]}
    htm = '<div class="card faq"><h2 style="font-size:16px;margin:0 0 8px">자주 묻는 질문</h2>' + "".join(
        f'<details{" open" if i < 2 else ""}><summary><b>{e(q)}</b></summary><p class="s13">{e(a)}</p></details>' for i, (q, a) in enumerate(qas)) + "</div>"
    return obj, htm


def meta_head(title, desc, url, extra=""):
    return (f'<link rel="canonical" href="{e(url)}">\n<meta name="description" content="{e(desc)}">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="티커맵"><meta property="og:locale" content="ko_KR">\n'
            f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(url)}">\n'
            f'<meta property="og:image" content="{SITE_URL}/{OG_IMAGE}"><meta name="twitter:card" content="summary_large_image">\n'
            f'<link rel="alternate" type="application/rss+xml" title="티커맵 새 소식" href="{SITE_URL}/hub/feed.xml">\n{extra}')


def inject(tpl, *, title, desc, path, var, body, image=None, jsonld=""):
    """템플릿 HTML에 base·메타·변수·미리 그린 본문을 넣음"""
    url = f"{SITE_URL}/{path}"
    head = '<base href="../../">\n' + meta_head(title, desc, url, jsonld) + f'<script>{var}</script>\n'
    s = re.sub(r'<meta name="description"[^>]*>\n?', "", tpl)              # 템플릿의 설명 메타는 빼고 새로
    s = s.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + head, 1) if '<meta charset="utf-8">' in s else s.replace("<head>", "<head>\n" + head, 1)
    s = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", s, count=1, flags=re.S)
    s = s.replace(SKEL, f'<div class="wrap" id="app">{body}</div>', 1)
    return s


def kv(items):
    return '<div class="kv">' + "".join(f"<div><span>{e(a)}</span><b>{e(b)}</b></div>" for a, b in items if b not in (None, "-", "")) + "</div>"


# ---- 종목 점검표 (web/assets/ui.js checklist()와 같은 규칙 — 거기를 바꾸면 여기도)
LENS = {
    "eps": ("EPS 전망", 0.3, False, lambda r: r["c_chg90"] if r.get("c_chg90") is not None and (r.get("c_n") or 0) >= 3 else None),
    "rev": ("매출 가속", 0.3, False, lambda r: r["rev_qg"] - r["rev_g"] if r.get("rev_qg") is not None and r.get("rev_g") is not None else None),
    "guru": ("유명 투자자", 5, False, lambda r: r.get("g13_chg")),
    "insider": ("내부자", 1, True, lambda r: (lambda n: (1 if n > 0 else -1) * max(0.05, min(1, (__import__("math").log10(abs(n)) - 4) / 4.5)) if n else None)((r.get("ib") or 0) - (r.get("is") or 0))),
    "short": ("공매도", 0.08, False, lambda r: -r["sv_chg60"] if r.get("sv_chg60") is not None else None),
}


def quad(x, yc):
    return "tl" if yc > 0.03 and x < -0.003 else "br" if yc < -0.03 and x > 0.003 else "tr" if yc >= 0 and x >= 0 else "bl"


def checklist(r, sec_fpe, asof):
    P = lambda v: "-" if v is None else f"{'+' if v > 0 else ''}{v * 100:.{1 if abs(v) < 0.1 else 0}f}%"
    pp = lambda v: f"{'+' if v > 0 else ''}{v * 100:.1f}%p"
    out = []
    br = []
    for k, (nm, mx, raw, f) in LENS.items():
        y = f(r)
        if y is None or r.get("r1m") is None:
            continue
        yc = y if raw else max(-1, min(1, y / mx))
        if quad(r["r1m"], yc) == "br":
            br.append(nm)
    if br:
        out.append(("warn", "주가는 오르는데 신호는 꺾임", f"티커맵 오른쪽 아래: {', '.join(br)} (1개월 주가 {P(r['r1m'])})"))
    if r.get("c_chg90") is not None and (r.get("c_n") or 0) >= 3:
        v = r["c_chg90"]; st = "good" if v > 0.03 else "warn" if v < -0.03 else "info"
        out.append((st, {"good": "이익 전망 상향 중", "warn": "이익 전망 하향 중", "info": "이익 전망 큰 변화 없음"}[st],
                    f"내년 EPS 전망 90일 {P(v)} · 30일 상향 {int(r.get('c_up') or 0)} / 하향 {int(r.get('c_dn') or 0)} (애널리스트 {int(r['c_n'])}명)"))
    if r.get("rev_qg") is not None and r.get("rev_g") is not None:
        a = r["rev_qg"] - r["rev_g"]; st = "good" if a > 0.02 else "warn" if a < -0.05 else "info"
        out.append((st, {"good": "매출 성장 빨라지는 중", "warn": "매출 성장 느려지는 중", "info": "매출 성장 속도 비슷"}[st], f"최근 분기 {P(r['rev_qg'])} vs 4개 분기 {P(r['rev_g'])} ({pp(a)})"))
    if r.get("om_chg") is not None and r.get("om") is not None:
        v = r["om_chg"]; st = "good" if v > 0.02 else "warn" if v < -0.03 else "info"
        out.append((st, {"good": "이익률 개선", "warn": "이익률 악화", "info": "이익률 비슷"}[st], f"영업이익률 {r['om'] * 100:.1f}% (1년 전보다 {pp(v)})"))
    ib, is_ = r.get("ib") or 0, r.get("is") or 0
    if ib >= 1e5:
        out.append(("good", "임원 장내 매수", f"최근 90일 매수 {usd(ib)}" + (f" ({int(r['ibn'])}명)" if r.get("ibn") else "") + (f" · 매도 {usd(is_)}" if is_ else "")))
    elif is_ and r.get("mcap") and is_ / r["mcap"] > 0.005:
        out.append(("warn", "내부자 매도 많음", f"최근 90일 매도 {usd(is_)} (시가총액의 {is_ / r['mcap'] * 100:.1f}%)"))
    elif is_ or ib:
        net = ib - is_
        out.append(("info", "내부자 거래 특이 사항 없음", f"최근 90일 순{'매수' if net >= 0 else '매도'} {usd(abs(net))}"))
    if r.get("g13_chg") is not None and (r.get("g13") or r.get("g13_chg")):
        v = r["g13_chg"]; st = "good" if v >= 2 else "warn" if v <= -2 else "info"
        out.append((st, {"good": "유명 투자자 매수 우위", "warn": "유명 투자자 매도 우위", "info": "유명 투자자 변화 적음"}[st], f"보유 {int(r.get('g13') or 0)}곳 · 순증 {'+' if v > 0 else ''}{int(v)} (13F, 분기 말 기준)"))
    if r.get("sv_chg60") is not None:
        v = r["sv_chg60"]; st = "warn" if v > 0.03 or (r.get("si") or 0) > 0.15 else "good" if v < -0.03 else "info"
        out.append((st, {"warn": "공매도 늘어남", "good": "공매도 줄어듦", "info": "공매도 변화 적음"}[st], f"거래 비중 60일 {pp(v)}" + (f" · 공매도 잔고 {r['si'] * 100:.1f}%" if r.get("si") is not None else "")))
    xs = sec_fpe.get(r.get("sec")) or []
    if (r.get("c_fpe") or 0) > 0 and len(xs) >= 8:
        med = xs[len(xs) // 2]; k = r["c_fpe"] / med; st = "warn" if k > 1.5 else "good" if k < 0.7 else "info"
        out.append((st, {"warn": "업종보다 비쌈", "good": "업종보다 쌈", "info": "업종과 비슷한 가격"}[st], f"선행 PER {r['c_fpe']:.1f}배 · {SECTOR_KO.get(r.get('sec'), r.get('sec'))} 중간값 {med:.1f}배"))
    if r.get("d200") is not None:
        v = r["d200"]
        out.append(("warn" if v < -0.1 else "good" if v > 0 else "info", "200일선 위" if v >= 0 else "200일선 아래", f"200일 평균 대비 {P(v)} · 52주 고가 대비 {P(r.get('hi52'))}"))
    order = {"warn": 0, "good": 1, "info": 2}
    return sorted(out, key=lambda x: order[x[0]])


def checklist_html(items):
    if not items:
        return ""
    ic = {"warn": ("⚠", "var(--warn)"), "good": ("✓", "var(--good)"), "info": ("·", "var(--muted)")}
    n = lambda st: sum(1 for x in items if x[0] == st)
    rows = "".join(f'<div class="ck-row"><span class="ck-ic" style="color:{ic[st][1]}">{ic[st][0]}</span><div><b>{e(t)}</b><div class="small mut">{e(d)}</div></div></div>' for st, t, d in items)
    return (f'<div class="card"><div class="ck"><div class="ck-head"><h2 style="font-size:16px;margin:0">종목 점검표</h2><span class="s13"><span style="color:var(--warn)">경고 {n("warn")}</span> · '
            f'<span style="color:var(--good)">우호 {n("good")}</span> · <span class="mut">참고 {n("info")}</span></span></div><div class="ck-list">{rows}</div>'
            f'</div></div>')


def amt(v):
    return "-" if v is None else usd(v) if abs(v) >= 1e6 else f"${v:,.2f}"


def er_text(L):
    """최근 실적 결과 한두 문장 (주가는 '발표 다음 날 반응'으로만 — 지금 주가와 섞지 않음)"""
    if not L:
        return ""
    parts = []
    for lab, x in (("EPS", L.get("eps")), ("매출", L.get("rev"))):
        if x and x.get("a") is not None:
            parts.append(f"{lab} {amt(x['a'])}" + (f"(예상 {amt(x['e'])}, {pct(x['s'])})" if x.get("e") is not None and x.get("s") is not None else ""))
    s = f"{mmdd(L['d'])}({wday(L['d'])}) 발표" + (f" — {L['verdict']}" if L.get("verdict") else "") + (". " + ", ".join(parts) if parts else "") + "."
    if L.get("mv") is not None:
        s += f" 발표 다음 날{('(' + mmdd(L['mv_d']) + ')') if L.get('mv_d') else ''} 주가 {pct(L['mv'])}" + (f"(평소 ±{L['avg'] * 100:.1f}%)" if L.get("avg") else "") + "."
    return s


def josa(w, a, b):
    """받침 있으면 a(은·이), 없으면 b(는·가). 한글이 아니면 a(b)"""
    c = (w or "")[-1:]
    if "가" <= c <= "힣":
        return w + (a if (ord(c) - 0xAC00) % 28 else b)
    return f"{w}{a}({b})"


def stock_page(tpl, r, d, ko, aliases, peers, is_etf, ck=None, etfs=None):
    t, n = r["t"], r.get("n") or r["t"]
    name = f"{ko}({t})" if ko else f"{n} ({t})"
    if is_etf:
        title = f"{t} ETF — {n} 구성 종목·배당·수익률 | 티커맵"
        desc = (f"{t} {n}: 종가 ${r.get('px') or 0:,.2f}, 순자산 {usd(r.get('aum'))}, 총보수 {pct(r.get('exp'), False) if r.get('exp') else '-'}, "
                f"1년 {pct(r.get('r1y'))}. 구성 종목·업종 비중·배당 이력·국내 상장 대응 ETF를 한국어로.")
        items = [("종가", f"${r.get('px') or 0:,.2f}"), ("순자산", usd(r.get("aum"))), ("총보수", pct(r.get("exp"), False) if r.get("exp") else None),
                 ("배당수익률", pct(r.get("dy"), False) if r.get("dy") else None), ("1개월", pct(r.get("r1m"))), ("1년", pct(r.get("r1y")))]
    else:
        cn = r.get("c_next") if r.get("c_next") and r["c_next"] >= (r.get("asof") or "") else None
        when = f" {r['c_when']}" if r.get("c_when") else ""
        tp = r["px"] * (1 + r["c_upside"]) if r.get("px") and r.get("c_upside") is not None else None
        nxt = f" 다음 실적 발표 {mmdd(cn)}({wday(cn)}){when}{' 예정' if r.get('c_est') else ''}." if cn else ""
        tpt = f" 평균 목표주가 ${tp:,.2f}({pct(r['c_upside'])})." if tp else ""
        title = f"{name} 주가·실적 발표일{' ' + mmdd(cn) if cn else ''}·목표주가 | 티커맵"
        s1c = " ".join(x for x in re.split(r"(?<=\.) ", r.get("s1") or "") if "실적 발표" not in x)
        desc = (f"{name} 주가 ${r.get('px') or 0:,.2f}({pct(r.get('r1d'))}), 시가총액 {usd(r.get('mcap'))}.{nxt}{tpt} "
                f"{s1c} 실적·애널리스트 전망·재무·내부자 거래·유명 투자자 보유를 한국어로.")
        items = [("종가", f"${r.get('px') or 0:,.2f}"), ("시가총액", usd(r.get("mcap"))), ("업종", SECTOR_KO.get(r.get("sec"), r.get("sec"))),
                 ("다음 실적 발표", r.get("c_next")), ("PER", f"{r['pe']:.1f}배" if r.get("pe") else None),
                 ("매출 성장(최근 4분기)", pct(r.get("rev_g")) if r.get("rev_g") is not None else None),
                 ("영업이익률", pct(r.get("om"), False) if r.get("om") is not None else None),
                 ("애널리스트 순상향률", pct(r.get("c_ratio")) if r.get("c_ratio") is not None else None),
                 ("목표가 상승여력", pct(r.get("c_upside")) if r.get("c_upside") is not None else None),
                 ("공매도 거래 비중", pct(r.get("sv"), False) if r.get("sv") is not None else None),
                 ("유명 투자자 보유", f"{int(r['g13'])}곳" if r.get("g13") else None), ("1년 수익률", pct(r.get("r1y")))]
    desc = re.sub(r"\s+", " ", desc).strip()[:300]
    summ = (d or {}).get("summary") or ""
    nm = ko or n
    extra, qas = "", []
    if not is_etf:
        L = ((d or {}).get("er") or {}).get("last")
        if L and L.get("d") and (dt.date.fromisoformat(r["asof"][:10]) - dt.date.fromisoformat(L["d"])).days <= 30:
            extra += f'<div class="card"><h2 style="font-size:16px;margin:0 0 6px">최근 실적 결과</h2><p class="s13" style="margin:0">{e(er_text(L))}</p></div>'
            qas.append((f"{nm} 최근 실적은 어땠나요?", er_text(L) + " (예상 = 발표 전날까지의 애널리스트 평균)"))
        cons = [("다음 실적 발표", f"{cn} ({wday(cn)}){when}" + (" · 예정일" if r.get("c_est") else "") if cn else None),
                ("평소 발표 때 주가 변동", f"±{r['er_avg'] * 100:.1f}%" if r.get("er_avg") else None),
                ("평균 목표주가", f"${tp:,.2f} ({pct(r['c_upside'])})" if tp else None),
                ("매수 의견 비중", pct(r.get("c_buy"), False) if r.get("c_buy") is not None else None),
                ("애널리스트 수", f"{int(r['c_n'])}명" if r.get("c_n") else None),
                ("내년 EPS 전망 90일 변화", pct(r.get("c_chg90")) if r.get("c_chg90") is not None else None),
                ("선행 PER", f"{r['c_fpe']:.1f}배" if r.get("c_fpe") else None)]
        if any(b for _, b in cons):
            extra += f'<div class="card"><h2 style="font-size:16px;margin:0 0 6px">실적 발표일·애널리스트 컨센서스</h2>{kv(cons)}</div>'
        extra += checklist_html(ck or [])
        if cn:
            qas.append((f"{nm} 다음 실적 발표일은 언제인가요?", f"{cn}({wday(cn)}) 미국 시간{when} 발표{' 예정(회사 확정 전 추정)' if r.get('c_est') else ' 예정'}이에요." +
                        (f" 최근 발표 때 주가는 다음 날 평균 ±{r['er_avg'] * 100:.1f}% 움직였어요." if r.get("er_avg") else "")))
        if tp:
            qas.append((f"{nm} 목표주가는 얼마인가요?", f"애널리스트 {int(r.get('c_n') or 0)}명의 평균 목표주가는 약 ${tp:,.2f}로, {r['asof']} 종가 ${r['px']:,.2f}보다 {pct(r['c_upside'])} 높아요" +
                        (f" (매수 의견 {pct(r['c_buy'], False)})" if r.get("c_buy") is not None else "") + ". 목표주가는 애널리스트 의견일 뿐 실제 주가를 보장하지 않아요."))
        qas.append((f"{josa(nm, '은', '는')} 어떤 회사인가요?", f"{SECTOR_KO.get(r.get('sec'), r.get('sec') or '')} 업종({r.get('ind') or '-'})의 미국 상장 기업으로, 시가총액은 {usd(r.get('mcap'))}예요." +
                    (f" 최근 4개 분기 매출 성장률 {pct(r['rev_g'])}, 영업이익률 {pct(r['om'], False)}." if r.get("rev_g") is not None and r.get("om") is not None else "")))
    else:
        qas.append((f"{t} ETF 총보수와 배당은?", f"총보수 {pct(r.get('exp'), False) if r.get('exp') else '-'}, 배당수익률 {pct(r.get('dy'), False) if r.get('dy') else '-'}, 순자산 {usd(r.get('aum'))}이에요."))
    fobj, fhtm = faq(qas)
    etfl = ('<div class="card"><h3>이 종목을 담은 ETF</h3><div class="pill-row">' + "".join(f'<a class="tag" href="s/{e(x)}/">{e(x)}</a>' for x in etfs) + "</div></div>") if etfs else ""
    alias = f'<p class="mut s13">다른 이름: {e(", ".join(aliases))}</p>' if aliases else ""
    peer = ('<div class="card"><h3>같은 업종 종목</h3><div class="pill-row">' +
            "".join(f'<a class="tag" href="{e(p_url)}">{e(p_lab)}</a>' for p_url, p_lab in peers) + "</div></div>") if peers else ""
    body = (f'<div class="hero"><h1>{e(t)} <span class="mut" style="font-size:17px">{e(ko + " · " if ko else "")}{e(n)}</span></h1>'
            f'{"<p>" + e(r["s1"]) + "</p>" if r.get("s1") else ""}</div>{extra}'
            f'<div class="card"><h2 style="font-size:16px;margin:0 0 6px">핵심 지표</h2>{kv(items)}{alias}'
            f'{"<p class=" + chr(34) + "mut s13" + chr(34) + ">" + e(summ[:600]) + "</p>" if summ else ""}'
            f'<p class="small faint">{e(r.get("asof") or "")} 기준 · 출처: SEC EDGAR, FINRA, yfinance · 정보 제공용이며 투자 권유가 아닙니다</p></div>{fhtm}{peer}{etfl}'
            f'<noscript><div class="card">전체 화면(차트·재무표·공시 목록)은 자바스크립트를 켜면 볼 수 있어요.</div></noscript>')
    jl = ld(crumbs(("티커맵", "hub/"), ("ETF" if is_etf else "종목", "hub/screen"), (name, f"hub/s/{t}/")), fobj)
    return inject(tpl, title=title, desc=desc, path=f"hub/s/{t}/", var=f"window.HUB_T={json.dumps(t)}", body=body, jsonld=jl)


def investor_page(tpl, m):
    kind = {"guru": "유명 투자자", "fund": "헤지펀드·퀀트", "inst": "대형 운용사"}[m["k"]]
    q = f"{m['p'][:4]}년 {(int(m['p'][5:7]) + 2) // 3}분기"
    top = [x for x in m["top"] if x.get("t")][:5]
    title = f"{m['m']} 13F 포트폴리오 ({q}) — 보유 종목·매수·매도 | 티커맵"
    desc = (f"{m['m']}의 {q} 말 13F 보유 종목: " + ", ".join(f"{x['t']} {x['w'] * 100:.1f}%" for x in top if x.get("w") is not None) +
            f". 총 {usd(m['total'])}, {m['n']}종목. 이번 분기 새로 산 종목과 판 종목을 한국어로.")
    def trow(x):
        t = x.get("t")
        link = '<a href="s/%s/"><b>%s</b></a>' % (e(t), e(t)) if t else "-"
        return ('<tr><td>%s</td><td class="l nm mut">%s</td><td class="num">%.1f%%</td><td class="num">%s</td></tr>'
                % (link, e((x.get("n") or "")[:30]), (x.get("w") or 0) * 100, usd(x.get("v"))))
    rows = "".join(trow(x) for x in m["top"][:20])
    n_pos = "{:,}".format(m["n"])
    buys = ", ".join(x["t"] for x in m.get("buys", [])[:8] if x.get("t"))
    sells = ", ".join(x["t"] for x in m.get("sells", [])[:8] if x.get("t"))
    body = (f'<div class="hero"><h1>{e(m["m"])}</h1><p>{e(kind)} · {e(q)} 말 기준 13F · {e(m["filed"])} 제출</p></div>'
            f'<div class="card">{kv([("보유 총액", usd(m["total"])), ("보유 종목 수", n_pos), ("상위 10종목 비중", pct(m.get("top10w"), False))])}'
            f'{"<p class=" + chr(34) + "s13" + chr(34) + ">이번 분기 산 종목: " + e(buys) + "</p>" if buys else ""}'
            f'{"<p class=" + chr(34) + "s13" + chr(34) + ">이번 분기 판 종목: " + e(sells) + "</p>" if sells else ""}</div>'
            f'<div class="card"><h3>보유 상위 종목</h3><div class="tbl-wrap"><table class="t"><thead><tr><th>종목</th><th class="l">발행사</th><th>비중</th><th>평가액</th></tr></thead><tbody>{rows}</tbody></table></div></div>')
    jl = ld(crumbs(("티커맵", "hub/"), ("유명 투자자", "hub/investors"), (m["m"], f"hub/i/{m['cik']}/")))
    return inject(tpl, title=title, desc=re.sub(r"\s+", " ", desc)[:300], path=f"hub/i/{m['cik']}/", var=f"window.HUB_M={m['cik']}", body=body, jsonld=jl)


def page_meta(s, *, title, desc, path, body=None, jsonld=""):
    """화면 파일(index·earnings·investors 등)에 제목·설명·대표 주소·미리 그린 본문"""
    s = re.sub(r'<meta name="description"[^>]*>\n?', "", s)
    s = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", s, count=1, flags=re.S)
    s = s.replace("<title>", meta_head(title, desc, f"{SITE_URL}/{path}", jsonld) + "<title>", 1)
    if body:
        s = s.replace(SKEL, f'<div class="wrap" id="app">{body}</div>', 1)
    return s


def tlink(r, names, extra=""):
    k = names.get(r["t"], (r.get("ko") or "", []))[0] or ""
    lab = f'<b>{e(r["t"])}</b>' + (f' <span class="mut">{e(k)}</span>' if k and k != r["t"] else "")
    return f'<a class="tag" href="s/{e(r["t"])}/">{lab}{e(extra)}</a>'


def prerender(site, U, names, f13):
    """홈·실적 달력·유명 투자자 목록 — 자바스크립트 화면이 그리기 전 HTML (검색엔진·느린 기기용)"""
    hub, asof = site / "hub", U["asof"]
    a0 = dt.date.fromisoformat(asof)
    S = [r for r in U["rows"] if r.get("k") == "stock"]
    by_mcap = lambda xs: sorted(xs, key=lambda r: -(r.get("mcap") or 0))
    upcoming = {}
    for r in S:
        cn = r.get("c_next")
        if cn and asof < cn <= (a0 + dt.timedelta(days=14)).isoformat():
            upcoming.setdefault(cn, []).append(r)
    days = sorted(upcoming)
    recent = by_mcap([r for r in S if r.get("er_d") and (a0 - dt.date.fromisoformat(r["er_d"])).days <= 7 and r.get("er_eps_s") is not None])
    out = {}
    # 실적 달력
    f = hub / "earnings.html"
    if f.exists() and days:
        d1, d2 = mmdd(days[0]), mmdd(days[-1])
        secs = "".join(f'<div class="card"><h2 style="font-size:16px;margin:0 0 8px">{mmdd(d)}({wday(d)}) · {len(upcoming[d])}개</h2><div class="pill-row">' +
                       "".join(tlink(r, names, f" · {r['c_when']}" if r.get("c_when") else "") for r in by_mcap(upcoming[d])[:24]) +
                       (f'<span class="mut s13">외 {len(upcoming[d]) - 24}개</span>' if len(upcoming[d]) > 24 else "") + "</div></div>" for d in days)
        rec = ('<div class="card"><h2 style="font-size:16px;margin:0 0 8px">최근 7일 발표 결과 (EPS, 예상 대비)</h2><div class="pill-row">' +
               "".join(tlink(r, names, f" {pct(r['er_eps_s'])}") for r in recent[:30]) + "</div></div>") if recent else ""
        top = ", ".join((names.get(r["t"], (None, []))[0] or r["t"]) for r in by_mcap([x for d in days[:5] for x in upcoming[d]])[:6])
        body = (f'<div class="hero"><h1>미국 주식 실적 발표 일정</h1><p>{asof} 기준 · {d1}~{d2} 실적을 발표하는 러셀 1000·나스닥 100 종목 (미국 시간, 장 전 = 개장 전 · 장 후 = 마감 뒤)</p></div>{rec}{secs}')
        title = f"미국 주식 실적 발표 일정 {d1}~{d2} — 이번 주·다음 주 | 티커맵"
        desc = f"이번 주·다음 주 미국 주식 실적 발표 일정({d1}~{d2}): {top} 등. 장 전·장 후 구분, 옵션이 예상하는 변동폭, 최근 발표 결과를 한국어로."
        out["earnings.html"] = page_meta(f.read_text(encoding="utf-8"), title=title, desc=desc, path="hub/earnings", body=body,
                                         jsonld=ld(crumbs(("티커맵", "hub/"), ("실적 달력", "hub/earnings"))))
    # 홈
    f = hub / "index.html"
    if f.exists():
        big = [r for r in S if (r.get("mcap") or 0) >= 1e10 and r.get("r1d") is not None]
        up = sorted(big, key=lambda r: -r["r1d"])[:10]
        dn = sorted(big, key=lambda r: r["r1d"])[:10]
        wk = by_mcap([x for d in days if d <= (a0 + dt.timedelta(days=7)).isoformat() for x in upcoming[d]])[:16]
        card = lambda h, xs, fx: f'<div class="card"><h2 style="font-size:16px;margin:0 0 8px">{h}</h2><div class="pill-row">' + "".join(tlink(r, names, fx(r)) for r in xs) + "</div></div>"
        body = ('<div class="hero"><h1>티커맵 — 미국 주식, 한눈에</h1><p>주가와 애널리스트 전망·유명 투자자·내부자·공매도가 어긋난 종목을 지도로 찾고, '
                '실적 발표일·컨센서스·재무·공시를 한국어로 봐요.</p></div>' +
                card(f"{asof} 많이 오른 종목 (시총 100억 달러 이상)", up, lambda r: f" {pct(r['r1d'])}") +
                card(f"{asof} 많이 내린 종목", dn, lambda r: f" {pct(r['r1d'])}") +
                (card("이번 주 실적 발표", wk, lambda r: f" {mmdd(r['c_next'])}") if wk else "") +
                '<div class="card"><div class="pill-row"><a class="tag" href="matrix">티커맵(어긋남 지도)</a><a class="tag" href="ranking">티커랭킹</a>'
                '<a class="tag" href="earnings">실적 달력</a><a class="tag" href="investors">유명 투자자</a><a class="tag" href="screen">종목 검색</a></div></div>')
        out["index.html"] = page_meta(f.read_text(encoding="utf-8"), title="티커맵 — 미국 주식 실적·컨센서스·유명 투자자를 한눈에",
                                      desc="미국 주식 1,000여 종목의 주가·실적 발표일·애널리스트 전망·재무·내부자 거래·유명 투자자 13F를 한국어로. 주가와 신호가 어긋난 종목을 지도로 찾아요.",
                                      path="hub/", body=body,
                                      jsonld=ld({"@context": "https://schema.org", "@type": "WebSite", "name": "티커맵", "alternateName": "TickerMap", "url": f"{SITE_URL}/hub/"}))
    # 유명 투자자 목록
    f = hub / "investors.html"
    if f.exists() and f13:
        K = {"guru": "유명 투자자", "fund": "헤지펀드·퀀트", "inst": "대형 운용사"}
        mg = f13.get("managers", [])
        secs = "".join(f'<div class="card"><h2 style="font-size:16px;margin:0 0 8px">{K[k]}</h2><div class="pill-row">' +
                       "".join(f'<a class="tag" href="i/{m["cik"]}/"><b>{e(m["m"])}</b> <span class="mut">{usd(m["total"])}</span></a>' for m in sorted([m for m in mg if m["k"] == k], key=lambda m: -(m.get("total") or 0))) +
                       "</div></div>" for k in K if any(m["k"] == k for m in mg))
        body = f'<div class="hero"><h1>유명 투자자 13F 포트폴리오</h1><p>버핏·애크먼·드러켄밀러 등 {len(mg)}곳이 분기마다 SEC에 낸 13F 보유 종목과 이번 분기 산·판 종목</p></div>{secs}'
        out["investors.html"] = page_meta(f.read_text(encoding="utf-8"), title=f"유명 투자자 13F 포트폴리오 — 버핏·애크먼 등 {len(mg)}곳 보유 종목 | 티커맵",
                                          desc=f"워런 버핏(버크셔)·빌 애크먼·드러켄밀러 등 유명 투자자 {len(mg)}곳의 13F 포트폴리오. 많이 가진 종목, 이번 분기 새로 산 종목과 판 종목을 한국어로.",
                                          path="hub/investors", body=body, jsonld=ld(crumbs(("티커맵", "hub/"), ("유명 투자자", "hub/investors"))))
    for k, v in out.items():
        (hub / k).write_text(v, encoding="utf-8")
    return out


def rfc822(d):
    t = dt.datetime.fromisoformat(d) if "T" in d else dt.datetime.fromisoformat(d[:10] + "T21:00:00")
    return t.strftime("%a, %d %b %Y %H:%M:%S +0000")


def feed(site, U, names, f13, results):
    """RSS — 최근 실적 결과·다가오는 실적 발표·새 13F (네이버 서치어드바이저·구독기용)"""
    asof, a0 = U["asof"], dt.date.fromisoformat(U["asof"])
    items = []
    for r, L in results:
        nm = names.get(r["t"], (r.get("ko"), []))[0]
        name = f"{nm}({r['t']})" if nm else f"{r.get('n') or r['t']} ({r['t']})"
        items.append((L["d"], f"{name} 실적 발표: {L.get('verdict') or '결과'}", f"hub/s/{r['t']}/", er_text(L)))
    up = {}
    for r in U["rows"]:
        cn = r.get("c_next")
        if r.get("k") == "stock" and cn and asof < cn <= (a0 + dt.timedelta(days=7)).isoformat():
            up.setdefault(cn, []).append(r)
    for d, xs in sorted(up.items()):
        xs = sorted(xs, key=lambda r: -(r.get("mcap") or 0))
        lab = ", ".join((names.get(r["t"], (None, []))[0] or r["t"]) + f"({r['t']})" for r in xs[:6])
        items.append((asof, f"{mmdd(d)}({wday(d)}) 미국 주식 실적 발표 예정: {lab}" + (f" 외 {len(xs) - 6}개" if len(xs) > 6 else ""),
                      "hub/earnings", f"{d} 실적 발표 예정 {len(xs)}개 종목: " + ", ".join(r["t"] + (f" {r['c_when']}" if r.get("c_when") else "") for r in xs[:30])))
    for m in (f13 or {}).get("managers", []):
        if m.get("filed") and (a0 - dt.date.fromisoformat(m["filed"])).days <= 45:
            q = f"{m['p'][:4]}년 {(int(m['p'][5:7]) + 2) // 3}분기"
            buys = ", ".join(x["t"] for x in m.get("buys", [])[:6] if x.get("t"))
            items.append((m["filed"], f"{m['m']} {q} 13F 공개" + (f" — 산 종목 {buys}" if buys else ""), f"hub/i/{m['cik']}/",
                          f"총 {usd(m['total'])}, {m['n']}종목." + (f" 산 종목: {buys}." if buys else "")))
    items.sort(key=lambda x: x[0], reverse=True)
    x = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
         "<title>티커맵 — 미국 주식 새 소식</title>", f"<link>{SITE_URL}/hub/</link>", "<description>미국 주식 실적 결과·실적 발표 일정·유명 투자자 13F를 한국어로</description>",
         "<language>ko</language>", f'<atom:link href="{SITE_URL}/hub/feed.xml" rel="self" type="application/rss+xml"/>', f"<lastBuildDate>{rfc822(asof)}</lastBuildDate>"]
    for d, t, u, dsc in items[:60]:
        x.append(f"<item><title>{e(t)}</title><link>{SITE_URL}/{u}</link><guid isPermaLink=\"false\">{e(u + '#' + d + '-' + t[:20])}</guid><pubDate>{rfc822(d)}</pubDate><description>{e(dsc)}</description></item>")
    x.append("</channel></rss>")
    (site / "hub" / "feed.xml").write_text("\n".join(x), encoding="utf-8")
    return len(items[:60])


def main(site):
    site = Path(site)
    hub, api = site / "hub", site / "api" / "v1"
    U = json.loads((api / "free" / "universe.json").read_text(encoding="utf-8"))
    meta = json.loads((api / "meta.json").read_text(encoding="utf-8")) if (api / "meta.json").exists() else {}
    lastmod = (meta.get("built") or dt.datetime.utcnow().isoformat())[:10]
    names = {}
    kp = ROOT / "hub" / "ko_names.csv"
    if kp.exists():
        for r in csv.DictReader(open(kp, encoding="utf-8")):
            names[r["ticker"]] = (r["ko"], [a.strip() for a in (r.get("aliases") or "").split(",") if a.strip()])
    tpl = (hub / "stock.html").read_text(encoding="utf-8")
    rows = U["rows"]
    by_sec = {}
    for r in rows:
        if r.get("k") == "stock" and r.get("sec"):
            by_sec.setdefault(r["sec"], []).append(r)
    for v in by_sec.values():
        v.sort(key=lambda r: -(r.get("mcap") or 0))
    sec_fpe = {k: sorted(x["c_fpe"] for x in v if (x.get("c_fpe") or 0) > 0) for k, v in by_sec.items()}
    urls = [("hub/", "1.0"), ("hub/matrix", "0.9"), ("hub/ranking", "0.8"), ("hub/earnings", "0.8"), ("hub/investors", "0.8"), ("hub/screen", "0.6"), ("hub/compare", "0.5")]   # .html 없는 주소 (Cloudflare Pages가 이쪽으로 보냄)
    n, results = 0, []
    for r in rows:
        t = r["t"]
        if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", t):
            continue
        is_etf = r.get("k") == "etf"
        f = api / "free" / ("etf" if is_etf else "stock") / f"{t}.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception:
            d = {}
        r = {**r, "asof": d.get("asof") or U.get("asof")}
        ko, aliases = names.get(t, (r.get("ko"), []))
        def plab(p):
            k = names.get(p["t"], (p.get("ko") or "", []))[0] or ""
            return p["t"] if not k or k == p["t"] else f"{p['t']} {k}"
        peers = [] if is_etf else [(f"s/{p['t']}/", plab(p)) for p in by_sec.get(r.get("sec"), []) if p["t"] != t][:10]
        out = hub / "s" / t / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        etfs = [x[0] for x in (d.get("etf_in") or [])[:8]] if not is_etf else None
        ck = None if is_etf else checklist(r, sec_fpe, r["asof"])
        L = ((d.get("er") or {}).get("last")) if not is_etf else None
        if L and L.get("d") and (dt.date.fromisoformat(U["asof"]) - dt.date.fromisoformat(L["d"])).days <= 7 and L.get("eps"):
            results.append((r, L))
        out.write_text(stock_page(tpl, r, d, ko, aliases, peers, is_etf, ck, etfs), encoding="utf-8")
        urls.append((f"hub/s/{t}/", "0.7" if (r.get("mcap") or r.get("aum") or 0) >= 1e10 else "0.5"))
        n += 1
    ni = 0
    fp = api / "free" / "f13.json"
    if fp.exists() and (hub / "investors.html").exists():
        itpl = (hub / "investors.html").read_text(encoding="utf-8")
        for m in json.loads(fp.read_text(encoding="utf-8")).get("managers", []):
            out = hub / "i" / str(m["cik"]) / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(investor_page(itpl, m), encoding="utf-8")
            urls.append((f"hub/i/{m['cik']}/", "0.6"))
            ni += 1
    f13 = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
    pre = prerender(site, U, names, f13)
    nf = feed(site, U, names, f13, results)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{e(SITE_URL + '/' + u)}</loc><lastmod>{lastmod}</lastmod><priority>{p}</priority></url>" for u, p in urls]
    sm.append("</urlset>")
    (site / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (site / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    canon(site)
    print(f"정적 페이지: 종목·ETF {n}개, 투자자 {ni}개, 미리 그린 화면 {len(pre)}개, RSS {nf}건, 사이트맵 {len(urls)}개 주소 ({SITE_URL})")


def canon(site):
    """화면 페이지마다 대표 주소(canonical) — github.io 사본·www 같은 중복 주소가 tickermap.kr로 모이게.
    주소 뒤 ?t= 로 내용이 바뀌는 stock·investors는 종목·투자자 정적 페이지가 대표라 건너뜀. 오프라인 안내는 검색 제외"""
    hub = site / "hub"
    skip = {"stock.html", "investors.html"}
    for f in hub.glob("*.html"):
        s = f.read_text(encoding="utf-8")
        if f.name == "offline.html":
            s = s.replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1)
        elif f.name not in skip and 'rel="canonical"' not in s:
            path = "hub/" if f.name == "index.html" else "hub/" + f.name[:-5]
            s = s.replace("<title>", f'<link rel="canonical" href="{SITE_URL}/{path}">\n<meta property="og:image" content="{SITE_URL}/{OG_IMAGE}">\n'
                          f'<link rel="alternate" type="application/rss+xml" title="티커맵 새 소식" href="{SITE_URL}/hub/feed.xml">\n<title>', 1)
        f.write_text(s, encoding="utf-8")
    # 없는 주소는 404 (Cloudflare Pages는 404.html이 없으면 첫 화면을 200으로 돌려줌)
    (site / "404.html").write_text("""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>페이지를 찾을 수 없어요 | 티커맵</title>
<style>body{margin:0;font-family:system-ui,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#fafaf8;color:#1c1b19;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px}
a{display:inline-block;margin-top:14px;padding:10px 16px;border-radius:10px;background:#1c1b19;color:#fff;text-decoration:none}p{color:#6b6a65}</style></head>
<body><div><h1 style="font-size:22px">페이지를 찾을 수 없어요</h1><p>주소가 바뀌었거나 없는 종목일 수 있어요.</p><a href="/hub/">티커맵 홈으로</a></div></body></html>""", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
