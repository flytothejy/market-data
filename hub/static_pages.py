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


def inject(tpl, *, title, desc, path, var, body, image=None):
    """템플릿 HTML에 base·메타·변수·미리 그린 본문을 넣음"""
    url = f"{SITE_URL}/{path}"
    head = (f'<base href="../../">\n<link rel="canonical" href="{e(url)}">\n<meta name="description" content="{e(desc)}">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="종목 허브"><meta property="og:locale" content="ko_KR">\n'
            f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(url)}">\n'
            f'<meta name="twitter:card" content="summary">\n<script>{var}</script>\n')
    s = re.sub(r'<meta name="description"[^>]*>\n?', "", tpl)              # 템플릿의 설명 메타는 빼고 새로
    s = s.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + head, 1) if '<meta charset="utf-8">' in s else s.replace("<head>", "<head>\n" + head, 1)
    s = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", s, count=1, flags=re.S)
    s = s.replace('<div class="wrap" id="app"><div class="loading">불러오는 중…</div></div>', f'<div class="wrap" id="app">{body}</div>', 1)
    return s


def kv(items):
    return '<div class="kv">' + "".join(f"<div><span>{e(a)}</span><b>{e(b)}</b></div>" for a, b in items if b not in (None, "-", "")) + "</div>"


def stock_page(tpl, r, d, ko, aliases, peers, is_etf):
    t, n = r["t"], r.get("n") or r["t"]
    name = f"{ko}({t})" if ko else f"{n} ({t})"
    if is_etf:
        title = f"{t} ETF — {n} 구성 종목·배당·수익률 | 종목 허브"
        desc = (f"{t} {n}: 종가 ${r.get('px') or 0:,.2f}, 순자산 {usd(r.get('aum'))}, 총보수 {pct(r.get('exp'), False) if r.get('exp') else '-'}, "
                f"1년 {pct(r.get('r1y'))}. 구성 종목·업종 비중·배당 이력·국내 상장 대응 ETF를 한국어로.")
        items = [("종가", f"${r.get('px') or 0:,.2f}"), ("순자산", usd(r.get("aum"))), ("총보수", pct(r.get("exp"), False) if r.get("exp") else None),
                 ("배당수익률", pct(r.get("dy"), False) if r.get("dy") else None), ("1개월", pct(r.get("r1m"))), ("1년", pct(r.get("r1y")))]
    else:
        nxt = f" 다음 실적 발표 {mmdd(r['c_next'])}." if r.get("c_next") else ""
        title = f"{name} 주가·실적 발표일·컨센서스 | 종목 허브"
        desc = (f"{name} 주가 ${r.get('px') or 0:,.2f}({pct(r.get('r1d'))}), 시가총액 {usd(r.get('mcap'))}.{nxt} "
                f"{r.get('s1') or ''} 애널리스트 전망·재무·공매도·내부자 거래·유명 투자자 보유를 한국어로 한눈에.")
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
    alias = f'<p class="mut s13">다른 이름: {e(", ".join(aliases))}</p>' if aliases else ""
    peer = ('<div class="card"><h3>같은 업종 종목</h3><div class="pill-row">' +
            "".join(f'<a class="tag" href="{e(p_url)}">{e(p_lab)}</a>' for p_url, p_lab in peers) + "</div></div>") if peers else ""
    body = (f'<div class="hero"><h1>{e(t)} <span class="mut" style="font-size:17px">{e(ko + " · " if ko else "")}{e(n)}</span></h1>'
            f'{"<p>" + e(r["s1"]) + "</p>" if r.get("s1") else ""}</div>'
            f'<div class="card">{kv(items)}{alias}'
            f'{"<p class=" + chr(34) + "mut s13" + chr(34) + ">" + e(summ[:600]) + "</p>" if summ else ""}'
            f'<p class="small faint">{e(r.get("asof") or "")} 기준 · 출처: SEC EDGAR, FINRA, yfinance · 정보 제공용이며 투자 권유가 아닙니다</p></div>{peer}'
            f'<noscript><div class="card">전체 화면(차트·재무표·공시 목록)은 자바스크립트를 켜면 볼 수 있어요.</div></noscript>')
    return inject(tpl, title=title, desc=desc, path=f"hub/s/{t}/", var=f"window.HUB_T={json.dumps(t)}", body=body)


def investor_page(tpl, m):
    kind = {"guru": "유명 투자자", "fund": "헤지펀드·퀀트", "inst": "대형 운용사"}[m["k"]]
    q = f"{m['p'][:4]}년 {(int(m['p'][5:7]) + 2) // 3}분기"
    top = [x for x in m["top"] if x.get("t")][:5]
    title = f"{m['m']} 13F 포트폴리오 ({q}) — 보유 종목·매수·매도 | 종목 허브"
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
    return inject(tpl, title=title, desc=re.sub(r"\s+", " ", desc)[:300], path=f"hub/i/{m['cik']}/", var=f"window.HUB_M={m['cik']}", body=body)


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
    urls = [("hub/", "1.0"), ("hub/matrix.html", "0.9"), ("hub/earnings.html", "0.8"), ("hub/investors.html", "0.8"), ("hub/screen.html", "0.6"), ("hub/compare.html", "0.5")]
    n = 0
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
        out.write_text(stock_page(tpl, r, d, ko, aliases, peers, is_etf), encoding="utf-8")
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
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{e(SITE_URL + '/' + u)}</loc><lastmod>{lastmod}</lastmod><priority>{p}</priority></url>" for u, p in urls]
    sm.append("</urlset>")
    (site / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (site / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    print(f"정적 페이지: 종목·ETF {n}개, 투자자 {ni}개, 사이트맵 {len(urls)}개 주소 ({SITE_URL})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
