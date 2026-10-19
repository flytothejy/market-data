"""뉴스 — 종목별 기사 제목(yfinance) + 기업 보도자료(RSS, 본문의 '(NASDAQ: XXX)' 표기로 종목 짝짓기)

저장: data/hub/news/YYYY-MM.parquet
  id, ticker, published(UTC), title, source, url, kind(news|press), summary(최대 300자)
본문은 저장하지 않음(저작권) — 제목·링크·요약만
어조 점수는 화면용 데이터 만들 때 별도로 계산
"""
import hashlib, html, re, time, datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import pandas as pd
import yfinance as yf

from .core import DATA, Http, Run, log, upsert
from . import universe

N_DIR = DATA / "news"
RSS = {
    "GlobeNewswire": "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire%20-%20News%20about%20Public%20Companies",
    "PR Newswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
    "Business Wire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFpRWQ==",
}
# 소송 권유 광고(법무법인), 다국어 중복본은 제외
SPAM = re.compile(r"securities fraud|class action|investors? (have|who|are encouraged)|shareholder alert|investor alert|law firm|"
                  r"rosen law|pomerantz|levi & korsinsky|bragar|faruqi|schall law|glancy|kessler topaz|bronstein|gross law|"
                  r"kirby mcinerney|robbins geller|sbs law|deadline (reminder|alert)|lead plaintiff", re.I)
NON_EN = re.compile(r"[àâçéèêëîïôûùüÿñæœäöß]")
TICK = re.compile(r"\((?:NASDAQ|Nasdaq|NYSE|NYSE American|NYSE Arca|Cboe|CBOE|NasdaqGS|NasdaqGM)\s*[:：]\s*([A-Z]{1,5}(?:[.\-][A-Z])?)\)")


def _id(url, title):
    return hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:16]


STATS = {"raw": 0, "keys": None}


def yf_news(t):
    out = []
    T = yf.Ticker(t)
    try:
        items = T.get_news(count=20) if hasattr(T, "get_news") else T.news
    except TypeError:
        items = T.news
    items = items or []
    STATS["raw"] += len(items)
    if items and STATS["keys"] is None:
        STATS["keys"] = list(items[0].keys())[:8] + list((items[0].get("content") or {}).keys())[:8]
    for it in items:
        c = it.get("content", it)
        title = c.get("title")
        url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link")
        src = (c.get("provider") or {}).get("displayName") or c.get("publisher")
        pub = c.get("pubDate") or c.get("displayTime")
        if pub:
            pub = pd.to_datetime(pub, utc=True, errors="coerce")
        elif c.get("providerPublishTime"):
            pub = pd.to_datetime(c["providerPublishTime"], unit="s", utc=True)
        if title and url:
            out.append({"id": _id(url, title), "ticker": t, "published": pub, "title": title, "source": src, "url": url,
                        "kind": "news", "summary": (c.get("summary") or "")[:300]})
    return out


def rss_press(http, keep):
    rows, stat = [], {}
    for name, url in RSS.items():
        try:
            root = ET.fromstring(http.get(url).content)
        except Exception as e:
            stat[name] = f"실패({str(e)[:30]})"
            continue
        items = root.findall(".//item")
        hit = 0
        for it in items:
            title = html.unescape((it.findtext("title") or "").strip())
            if SPAM.search(title) or len(NON_EN.findall(title)) >= 2:
                continue
            link = (it.findtext("link") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
            cats = " ".join(c.text or "" for c in it.findall("category"))
            ts = set(TICK.findall(f"{title} {desc} {cats}"))
            try:
                pub = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate"))).tz_convert("UTC")
            except Exception:
                pub = pd.NaT
            for t in ts:
                t = t.replace(".", "-")
                if t in keep:
                    hit += 1
                    rows.append({"id": _id(link, title) + t, "ticker": t, "published": pub, "title": title, "source": name,
                                 "url": link, "kind": "press", "summary": " ".join(desc.split())[:300]})
        stat[name] = f"{len(items)}건 중 대상 {hit}"
    return rows, stat


YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"


def yahoo_rss(http, t):
    """yfinance 뉴스가 비어 있을 때 쓰는 야후 종목 RSS"""
    r = http.get(YAHOO_RSS.format(t=t), ok404=True)
    if r is None:
        return []
    out = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        try:
            pub = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate"))).tz_convert("UTC")
        except Exception:
            pub = pd.NaT
        if title and link:
            out.append({"id": _id(link, title), "ticker": t, "published": pub, "title": title, "source": "Yahoo Finance",
                        "url": link, "kind": "news", "summary": re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:300]})
    return out


def run(limit=0, **_):
    R = Run("news")
    U = universe.load("stock")
    tickers = list(U.ticker)
    if limit:
        tickers = tickers[:limit]
    rows, fail = [], []
    http = Http(rate=3)
    use_rss = False
    for i, t in enumerate(tickers):
        try:
            got = [] if use_rss else yf_news(t)
            if not got:
                got = yahoo_rss(http, t)
                if got and i < 5 and STATS["raw"] == 0:
                    use_rss = True          # yfinance가 계속 비면 처음부터 RSS로
            rows += got
        except Exception as e:
            fail.append(t)
        time.sleep(0.15)
        if (i + 1) % 200 == 0:
            log(f"  뉴스 {i+1}/{len(tickers)}")
    press, stat = rss_press(Http(rate=1), set(U.ticker))
    rows += press
    if not rows:
        R.warning("치명: 받은 기사가 없음")
        return R.done(ok=False)
    A = pd.DataFrame(rows)
    A["published"] = pd.to_datetime(A["published"], utc=True, errors="coerce")
    A = A.drop_duplicates(["id", "ticker"]).drop_duplicates(["ticker", "title"])
    A["ym"] = A.published.dt.strftime("%Y-%m").fillna("unknown")
    for ym, g in A.groupby("ym"):
        upsert(N_DIR / f"{ym}.parquet", g.drop(columns="ym"), ["id", "ticker"], sort=["published", "id"])
    news = A[A.kind == "news"]
    recent = news[news.published >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)]
    if fail:
        R.warning(f"뉴스 실패 {len(fail)}개: {', '.join(fail[:10])}")
    R.set(yf_raw_items=STATS["raw"])
    if STATS["raw"] and news.empty:
        R.warning(f"yfinance 기사 {STATS['raw']}건을 받았지만 해석 0건 — 항목 키: {STATS['keys']}")
    if not STATS["raw"]:
        R.set(news_source="야후 RSS (yfinance 뉴스 0건)")
    R.set(tickers=len(tickers), articles=len(news), tickers_with_news=news.ticker.nunique(),
          last48h=len(recent), press_releases=int((A.kind == "press").sum()), rss=", ".join(f"{k} {v}" for k, v in stat.items()),
          latest=str(A.published.max()), rows_new=len(A),
          busiest_48h=", ".join(f"{k} {v}" for k, v in recent.ticker.value_counts().head(5).items()) or "-")
    return R.done()
