"""재무 보충 — SEC companyfacts에 아직 반영되지 않은 보고서를 공시 원본 XBRL에서 직접 읽음

2026-10 점검에서 companyfacts가 7월 말 제출된 10-Q를 88개 대기업(코카콜라·애벗·포드·휴매나 등)에 대해
석 달째 반영하지 않은 것을 확인 → 최근 4개 분기 합계가 한 분기 밀림
해당 보고서의 인스턴스 문서(*_htm.xml 또는 *.xml)에서 차원(segment) 없는 값만 골라 facts와 같은 형식으로 만든다
"""
import re
from lxml import etree

from .sec import TAGS, FACT_COLS

NS_TAX = {"us-gaap": "us-gaap", "ifrs-full": "ifrs-full", "dei": "dei"}


def find_instance(http, cik, accession):
    acc = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/"
    j = http.get(base + "index.json").json()
    names = [i["name"] for i in j["directory"]["item"]]
    inst = [n for n in names if n.endswith("_htm.xml")]
    if not inst:          # 예전 방식: 인스턴스 이름이 회사-날짜.xml (스키마·링크베이스 제외)
        inst = [n for n in names if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$|FilingSummary", n)]
    return base + inst[0] if inst else None


def parse_instance(raw, cik, form, filed, accn):
    root = etree.fromstring(raw, parser=etree.XMLParser(huge_tree=True, recover=True))
    nsmap = {k: v for k, v in root.nsmap.items() if k}
    xbrli = "http://www.xbrl.org/2003/instance"
    ctx = {}
    for c in root.iter(f"{{{xbrli}}}context"):
        if c.find(f".//{{{xbrli}}}segment") is not None or c.find(f".//{{{xbrli}}}scenario") is not None:
            continue                                   # 사업부·지역 등 세부 값은 제외
        p = c.find(f"{{{xbrli}}}period")
        s, e, i = (p.findtext(f"{{{xbrli}}}{k}") for k in ("startDate", "endDate", "instant"))
        ctx[c.get("id")] = (s, e or i)
    units = {}
    for u in root.iter(f"{{{xbrli}}}unit"):
        meas = [m.text.split(":")[-1] for m in u.iter(f"{{{xbrli}}}measure")]
        units[u.get("id")] = "/".join(meas) if len(meas) <= 2 else meas[0]
        div = u.find(f"{{{xbrli}}}divide")
        if div is not None:
            num = div.find(f"{{{xbrli}}}unitNumerator").findtext(f".//{{{xbrli}}}measure").split(":")[-1]
            den = div.find(f"{{{xbrli}}}unitDenominator").findtext(f".//{{{xbrli}}}measure").split(":")[-1]
            units[u.get("id")] = f"{num}/{den}"
    fy = fp = None
    for prefix, uri in nsmap.items():
        if prefix == "dei":
            fy = root.findtext(f"{{{uri}}}DocumentFiscalYearFocus")
            fp = root.findtext(f"{{{uri}}}DocumentFiscalPeriodFocus")
    rows = []
    for tax, tags in TAGS.items():
        uri = next((u for p, u in nsmap.items() if p == tax or u.rstrip("/").split("/")[-2:-1] == [tax]), None)
        if uri is None:
            uri = next((u for u in nsmap.values() if f"/{tax}/" in u), None)
        if uri is None:
            continue
        for tag in tags:
            for el in root.iter(f"{{{uri}}}{tag}"):
                c = ctx.get(el.get("contextRef"))
                if c is None or el.text is None or el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                    continue
                try:
                    val = float(el.text.strip())
                except ValueError:
                    continue
                rows.append((int(cik), tax, tag, units.get(el.get("unitRef"), "USD"), c[0], c[1], val,
                             int(fy) if fy and fy.isdigit() else None, fp, form, filed, accn, None))
    return list({(r[2], r[3], r[4], r[5]): r for r in rows}.values())   # 같은 값 중복 제거
