"""과제 2-4-00b: 받아 둔 위키 판본에서 '구성 종목' 절만 읽어 구성 종목을 다시 뽑는다(다른 목록의 티커가 섞이는 문제 수정)."""
import os, re, io, json, glob
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "raw", "sb", "ndx_wiki")
def section(h):
    # 'Components' / 'Current components' 같은 h2 절
    hs = [m for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", h, re.S)]
    for i, m in enumerate(hs):
        title = re.sub("<[^>]+>", "", m.group(1)).lower()
        if "component" in title or "constituent" in title:
            end = hs[i + 1].start() if i + 1 < len(hs) else len(h)
            return h[m.end():end]
    return None
def parse(h):
    s = section(h)
    if s is None: return None, "nosection"
    try:
        for t in pd.read_html(io.StringIO(s)):
            cols = {str(c).lower(): c for c in t.columns}
            k = [c for l, c in cols.items() if "ticker" in l or "symbol" in l]
            if k and len(t) >= 80:
                col = t[k[0]]
                col = col.iloc[:, 0] if isinstance(col, pd.DataFrame) else col
                return sorted({str(x).strip() for x in col if str(x).strip() not in ("nan", "")}), "table"
    except ValueError: pass
    tk = re.findall(r"<li[^>]*>.*?\((?:NASDAQ:\s*)?(?:<a[^>]*>)?([A-Z][A-Z.]{0,5})(?:</a>)?\)", s)
    if len(tk) < 80:   # 깨진 렌더: 틀 안 위키 원문 '#[[회사]] (TICK)'
        tk = re.findall(r"#\[\[[^\]]+\]\][^(\\#]*\(([A-Z][A-Z.]{0,5})\)", s)
        return sorted(set(tk)), "wikitext"
    return sorted(set(tk)), "list"
rows = []
for f in sorted(glob.glob(os.path.join(D, "*_*.html"))):
    y, tag = os.path.basename(f)[:-5].split("_")
    tk, how = parse(open(f).read()); rev = json.load(open(f + ".json"))
    rows.append({"year": int(y), "tag": tag, "revid": rev["revid"], "ts": rev["timestamp"], "how": how, "n": len(tk or []), "tickers": ",".join(tk or [])})
M = pd.DataFrame(rows).sort_values(["year", "tag"], ascending=[True, False]); M.to_csv(os.path.join(D, "members.csv"), index=False)
print(M[["year", "tag", "ts", "how", "n"]].to_string(index=False))
