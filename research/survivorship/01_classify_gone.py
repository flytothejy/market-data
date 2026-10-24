"""생존편향 1: 2006년 이후 S&P 500에서 빠졌고 우리 데이터에 없는 종목을 분류한다.

입력 (research/data/raw/sb/)
- sp500_gone.csv          : 빠진 종목 목록 (sp500_hist.csv에서 계산)
- wiki_members_hist.csv   : 위키백과 S&P 500 목록 과거 판본에서 모은 티커·회사명·CIK (2014년 이후 판본만 CIK 있음)
- wiki_changes.csv        : 위키백과 편입·편출 내역과 사유
- cik-lookup-data.txt     : SEC 전체 회사명→CIK (과거 이름 포함)
- company_tickers.json    : SEC 현재 티커→CIK

절차
1. 티커 → CIK: 위키백과 CIK가 있으면 그것, 없으면 회사명 정규화 일치(유일할 때만).
2. CIK가 현재 우리 유니버스 종목의 CIK와 같으면 → '같은 회사(이름·티커 변경)': 이미 데이터에 있음.
3. 나머지는 SEC 제출 이력(data.sec.gov submissions)으로 마지막 공시일, 15·25 신고, 파산(8-K 1.03) 여부를 확인하고,
   위키백과 사유 문구와 합쳐 인수·합병 / 강등 / 파산·부진 / 미상으로 분류.
출력: research/survivorship/out/gone_classified.csv, 요약 출력
"""
import os, re, json, time
import pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SB = os.path.join(ROOT, "data", "raw", "sb")
OUT = os.path.join(ROOT, "survivorship", "out")
CACHE = os.path.join(SB, "subs")
os.makedirs(OUT, exist_ok=True); os.makedirs(CACHE, exist_ok=True)
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}

SUFFIX = r"\b(THE|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|COS|LTD|LIMITED|PLC|HOLDINGS?|GROUP|LP|LLC|NV|SA|AG|TRUST)\b"
def norm(s):
    s = str(s).upper().replace("&", " AND ")
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()

gone = pd.read_csv(os.path.join(SB, "sp500_gone.csv"), parse_dates=["first", "last"])
wm = pd.read_csv(os.path.join(SB, "wiki_members_hist.csv"))
wm["t"] = wm["t"].str.replace(".", "-", regex=False).str.strip()
ch = pd.read_csv(os.path.join(SB, "wiki_changes.csv")); ch["date"] = pd.to_datetime(ch["date"], errors="coerce")

# SEC 이름 → CIK
look = {}
with open(os.path.join(SB, "cik-lookup-data.txt"), encoding="latin-1") as f:
    for line in f:
        p = line.rstrip("\n").rsplit(":", 2)
        if len(p) < 3:
            continue
        look.setdefault(norm(p[0]), set()).add(int(p[1]))
cur = pd.DataFrame(json.load(open(os.path.join(SB, "company_tickers.json"))).values())
cur["ticker"] = cur["ticker"].str.replace(".", "-", regex=False)
t2cik = dict(zip(cur["ticker"], cur["cik_str"]))
uni = pd.read_csv(os.path.join(ROOT, "data", "universe.csv"))
uni_cik = {t2cik.get(t.replace(".", "-")) for t in uni["t"]} - {None}

def resolve(t):
    w = wm[wm["t"] == t.replace(".", "-")]
    names = list(dict.fromkeys(w["name"].dropna()))
    ciks = {int(c) for c in w["cik"].dropna()}
    r = ch[ch["rem_t"] == t]
    if len(r):
        names += [n for n in r["rem_n"].dropna() if n not in names]
    if ciks:
        return names, min(ciks), "wiki_cik"
    for n in names:
        c = look.get(norm(n), set())
        if len(c) == 1:
            return names, next(iter(c)), "name_unique"
    for n in names:
        c = look.get(norm(n), set())
        if len(c) > 1:
            return names, sorted(c), "name_multi"
    return names, None, "none"

def subs(cik):
    p = os.path.join(CACHE, f"{cik}.json")
    if os.path.exists(p):
        return json.load(open(p))
    for att in range(3):
        r = requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", headers=H, timeout=30)
        if r.status_code == 200:
            j = r.json(); json.dump(j, open(p, "w")); time.sleep(0.15); return j
        time.sleep(2)
    return None

def filing_facts(j):
    rec = j.get("filings", {}).get("recent", {})
    forms, dates, items = rec.get("form", []), rec.get("filingDate", []), rec.get("items", [""] * len(rec.get("form", [])))
    out = {"name_sec": j.get("name"), "former": "; ".join(x["name"] for x in j.get("formerNames", [])[:4]),
           "tickers_now": ",".join(j.get("tickers", [])), "last_filing": max(dates) if dates else None,
           "last_10k": max((d for f, d in zip(forms, dates) if f in ("10-K", "10-K405")), default=None),
           "form15": any(f.startswith("15") for f in forms), "form25": any(f.startswith("25") for f in forms),
           "bankr_dates": ";".join(d for f, d, it in zip(forms, dates, items)
                                   if f == "8-K" and "1.03" in [x.strip() for x in (it or "").split(",")])}
    return out

def reason_class(s):
    s = str(s).lower()
    if re.search(r"bankrupt|chapter 11|delist|insolven|receivership|seized|conservator", s): return "파산·부진"
    if re.search(r"acqui|merg|purchas|bought|takeover|taken private|buyout|combin", s): return "인수·합병"
    if re.search(r"spin|split", s): return "분할"
    if re.search(r"market cap|capitaliz|representative|liquidity|float|small|low", s): return "강등"
    return None

uni_t = set(uni["t"].str.replace(".", "-", regex=False))

def pick_multi(cands, removed):
    """후보 CIK 여럿 → 편출일 전 3년 안에 10-K를 낸 후보 중 편출일에 가장 가까운 것."""
    best, gap = None, None
    for c_ in cands:
        j = subs(c_)
        if not j:
            continue
        rec = j.get("filings", {}).get("recent", {})
        ds = [pd.Timestamp(d) for f, d in zip(rec.get("form", []), rec.get("filingDate", [])) if f in ("10-K", "10-K405")]
        ds = [d for d in ds if removed - pd.Timedelta(days=1100) <= d <= removed + pd.Timedelta(days=400)]
        if ds:
            g_ = min(abs((d - removed).days) for d in ds)
            if gap is None or g_ < gap:
                best, gap = c_, g_
    return best

rows = []
for _, g in gone.iterrows():
    names, cik, how = resolve(g["t"])
    if isinstance(cik, list):
        p = pick_multi(cik, g["last"])
        if p:
            cik, how = p, "name_multi_picked"
    rec = {"t": g["t"], "first": g["first"].date(), "last": g["last"].date(), "names": " | ".join(names[:3]),
           "cik": cik if not isinstance(cik, list) else ",".join(map(str, cik[:5])), "cik_how": how}
    r = ch[(ch["rem_t"] == g["t"]) & (ch["date"] >= "2005-12-01")]
    rec["wiki_reason"] = str(r.iloc[0]["reason"])[:160] if len(r) else None
    single = cik if isinstance(cik, int) else None
    f = filing_facts(subs(single)) if single else {}
    rec.update(f)
    now = [x.replace(".", "-") for x in (f.get("tickers_now") or "").split(",") if x]
    bare = re.sub(r"\s*\(.*", "", g["t"])
    if (single and single in uni_cik) or any(x in uni_t for x in now):
        rec["class"], rec["rule"] = "같은 회사(이름·티커 변경)", "cik"
    elif re.fullmatch(r"[A-Z]{3,4}Q{1,2}", bare) and len(bare) >= 5 or bare in ("FNMA", "FMCC"):
        rec["class"], rec["rule"] = "파산·부진", "Q접미사/정부관리"
    elif any(-365 <= (pd.Timestamp(d) - g["last"]).days <= 90 for d in (f.get("bankr_dates") or "").split(";") if d):
        rec["class"], rec["rule"] = "파산·부진", "8-K 1.03 (편출 1년 전~90일 뒤)"
    elif rec["wiki_reason"] and reason_class(rec["wiki_reason"]):
        rc = reason_class(rec["wiki_reason"])
        rec["class"] = "강등(아직 상장)" if rc == "강등" and now else rc
        rec["rule"] = "위키 사유"
    elif now:
        rec["class"], rec["rule"] = "강등(아직 상장)", "SEC 현재 티커"
    elif (f.get("form15") or f.get("form25")) and f.get("last_10k") and \
            pd.Timestamp(f["last_10k"]) <= g["last"] + pd.Timedelta(days=400):
        rec["class"], rec["rule"] = "인수·합병(추정)", "편출 뒤 1년 안 10-K 중단 + 등록 말소"
    else:
        rec["class"], rec["rule"] = "미상", "-"
    rows.append(rec)

c = pd.DataFrame(rows)
c.to_csv(os.path.join(OUT, "gone_classified.csv"), index=False)
c["year"] = pd.to_datetime(c["last"]).dt.year
pd.set_option("display.width", 220, "display.max_colwidth", 60)
print(c["cik_how"].value_counts().to_string())
print(c["class"].value_counts().to_string())
print(pd.crosstab(pd.cut(c["year"], [2005, 2009, 2014, 2019, 2026], labels=["2006-09", "10-14", "15-19", "20-25"]), c["class"]).to_string())
