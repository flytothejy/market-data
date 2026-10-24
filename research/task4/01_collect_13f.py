"""과제 4-01: 구루 36곳의 13F-HR 정보표를 SEC EDGAR에서 수집 (보고 분기 2013-06-30~)."""
import os, re, json, time
import pandas as pd, requests
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = os.path.join(ROOT, "data", "raw", "r2"); RAW = os.path.join(ROOT, "data", "raw", "f13"); os.makedirs(RAW, exist_ok=True)
H = {"User-Agent": "tickermap-research flytothejy@gmail.com"}
S = requests.Session(); S.headers.update(H)

def get(url, js=True):
    for a in range(4):
        r = S.get(url, timeout=60)
        if r.status_code == 200:
            time.sleep(0.12); return r.json() if js else r.text
        time.sleep(1 + 2 * a)
    return None

m = pd.read_parquet(os.path.join(R2, "f13__managers.parquet"))
m = m[m["kind"] == "guru"]
rows, flist = [], []
for cik, name in zip(m["manager_cik"], m["manager"]):
    j = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if not j:
        print("FAIL subs", cik); continue
    recs = [j["filings"]["recent"]] + [get(f"https://data.sec.gov/submissions/{f['name']}") for f in j["filings"].get("files", [])]
    fl = []
    for r in recs:
        if not r: continue
        for fm, fd, acc, rd in zip(r["form"], r["filingDate"], r["accessionNumber"], r.get("reportDate", [""] * len(r["form"]))):
            if fm in ("13F-HR", "13F-HR/A") and rd and rd >= "2013-06-30":
                fl.append((fm, fd, acc, rd))
    fl = pd.DataFrame(fl, columns=["form", "filed", "acc", "period"]).sort_values("filed")
    # 분기마다 원본 우선(가장 먼저 낸 13F-HR), 없으면 첫 수정본
    pick = []
    for per, g in fl.groupby("period"):
        o = g[g["form"] == "13F-HR"]
        pick.append((o if len(o) else g).iloc[0])
    for p in pick:
        cache = os.path.join(RAW, f"{cik}_{p['acc']}.csv")
        if os.path.exists(cache):
            rows.append(pd.read_csv(cache, dtype={"cusip": str})); flist.append((cik, name, *p)); continue
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{p['acc'].replace('-', '')}"
        idx = get(base + "/index.json")
        if not idx: print("FAIL idx", cik, p["acc"]); continue
        xmls = [it["name"] for it in idx["directory"]["item"] if it["name"].lower().endswith(".xml") and "primary_doc" not in it["name"].lower()]
        recs_ = []
        for xn in xmls:
            txt = get(f"{base}/{xn}", js=False)
            if not txt or "infoTable" not in txt: continue
            txt = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", txt); txt = re.sub(r"<(/?)\w+:", r"<\1", txt)
            txt = re.sub(r'\s[\w-]+:[\w-]+="[^"]*"', "", txt)
            root = ET.fromstring(txt.encode())
            for it in root.iter("infoTable"):
                g_ = lambda k: (it.findtext(k) or "").strip()
                recs_.append({"cusip": g_("cusip").upper(), "issuer": g_("nameOfIssuer"), "value": float(g_("value") or 0),
                              "shares": float(it.findtext("shrsOrPrnAmt/sshPrnamt") or 0),
                              "sh_type": (it.findtext("shrsOrPrnAmt/sshPrnamtType") or "").strip(), "put_call": g_("putCall")})
            break
        d = pd.DataFrame(recs_)
        if d.empty: print("EMPTY", cik, p["acc"]); continue
        d["manager_cik"], d["period"], d["filed"], d["acc"], d["form"] = cik, p["period"], p["filed"], p["acc"], p["form"]
        d.to_csv(cache, index=False); rows.append(d); flist.append((cik, name, *p))
    print(name, len(pick), flush=True)

h = pd.concat(rows, ignore_index=True)
h.to_parquet(os.path.join(RAW, "holdings_hist.parquet"))
pd.DataFrame(flist, columns=["cik", "manager", "form", "filed", "acc", "period"]).to_csv(os.path.join(RAW, "filings.csv"), index=False)
print("rows", len(h), "managers", h["manager_cik"].nunique(), "filings", h["acc"].nunique(), "cusips", h["cusip"].nunique())
