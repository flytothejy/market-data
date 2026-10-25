"""과제 2-4-00: 위키백과 'Nasdaq-100' 판본에서 연도별 구성 종목 수집 (정답 자료). 12월 재구성 전(11월 말)·후(1월 초) 판본."""
import os, time, json, re, io, requests, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "sb", "ndx_wiki"); os.makedirs(OUT, exist_ok=True)
S = requests.Session(); S.headers.update({"User-Agent": "tickermap-research flytothejy@gmail.com"})
API = "https://en.wikipedia.org/w/api.php"
def get(params):
    for k in range(6):
        r = S.get(API, params={**params, "format": "json"}, timeout=60)
        if r.status_code == 200: return r.json()
        time.sleep(60 * (k + 1))
    raise RuntimeError(r.status_code)
rows = []
for y in range(2007, 2027):
    for tag, ts in (("pre", f"{y-1}-11-30T00:00:00Z"), ("post", f"{y}-01-15T00:00:00Z")):
        f = os.path.join(OUT, f"{y}_{tag}.html")
        if not os.path.exists(f):
            j = get({"action": "query", "prop": "revisions", "titles": "Nasdaq-100", "rvlimit": 1, "rvdir": "older", "rvstart": ts, "rvprop": "ids|timestamp"})
            rev = list(j["query"]["pages"].values())[0]["revisions"][0]
            h = get({"action": "parse", "oldid": rev["revid"], "prop": "text"})["parse"]["text"]["*"]
            open(f, "w").write(h); json.dump(rev, open(f + ".json", "w")); time.sleep(6)
        rev = json.load(open(f + ".json")); html = open(f).read()
        best = None
        try: tabs = pd.read_html(io.StringIO(html))
        except ValueError: tabs = []
        for t in tabs:
            cols = [str(c).lower() for c in t.columns]
            tc = [c for c, l in zip(t.columns, cols) if "ticker" in l or "symbol" in l]
            if tc and 80 <= len(t) <= 110: best = t[tc[0]].astype(str).str.strip().tolist(); break
        if best is None:  # 옛 판본: 목록 형식 '회사 (TICK)'
            best = sorted(set(re.findall(r"\((?:NASDAQ:\s*)?(?:<a[^>]*>)?([A-Z][A-Z.]{0,5})(?:</a>)?\)\s*(?:</li>|<br|,|\n)", html)))
        rows.append({"year": y, "tag": tag, "revid": rev["revid"], "ts": rev["timestamp"], "n": len(best), "tickers": ",".join(best)})
        print(y, tag, rev["timestamp"], len(best))
pd.DataFrame(rows).to_csv(os.path.join(OUT, "members.csv"), index=False)
