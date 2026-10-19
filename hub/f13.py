"""13F 기관 보유 — 유명 투자자·대형 운용사 약 40곳의 분기 보유 종목 (SEC 13F-HR 정보표)

전체 8,000여 기관 대신 '구루 포트폴리오'와 대형 운용사로 한정 (유지 부담 ↓, 한국 투자자 관심 ↑)
CIK는 SEC 등록 이름과 대조해 다르면 건너뜀 (번호 착오로 엉뚱한 기관을 받는 것 방지)
저장
  data/hub/f13/holdings.parquet  manager_cik, manager, period, filed, accession, cusip, issuer, cls, value_usd, shares, put_call, ticker
  data/hub/f13/managers.parquet  확인된 기관 목록
티커 매핑: CUSIP → SPDR ETF 보유 파일의 식별번호 + SEC 회사명 대조 (매핑 안 된 건 ticker 비움)
"""
import re, datetime as dt
import xml.etree.ElementTree as ET
import pandas as pd

from .core import DATA, Run, log, read, sec_http, upsert, write
from . import universe

F_DIR = DATA / "f13"
# (CIK, 이름 확인용 키워드, 한국어 표시명)
MANAGERS = [
    (1067983, "BERKSHIRE", "버크셔 해서웨이 (워런 버핏)"), (1336528, "PERSHING", "퍼싱스퀘어 (빌 애크먼)"),
    (1649339, "SCION", "사이언 (마이클 버리)"), (1656456, "APPALOOSA", "아팔루사 (데이비드 테퍼)"),
    (1061768, "BAUPOST", "바우포스트 (세스 클라만)"), (1536411, "DUQUESNE", "듀케인 패밀리오피스 (드러켄밀러)"),
    (1040273, "THIRD POINT", "서드포인트 (댄 롭)"), (1167483, "TIGER GLOBAL", "타이거 글로벌"),
    (1135730, "COATUE", "코투 매니지먼트"), (1029160, "SOROS", "소로스 펀드"), (1350694, "BRIDGEWATER", "브리지워터 (레이 달리오)"),
    (1037389, "RENAISSANCE", "르네상스 테크놀로지"), (1423053, "CITADEL", "시타델"), (1103804, "VIKING", "바이킹 글로벌"),
    (1061165, "LONE PINE", "론파인 캐피탈"), (1079114, "GREENLIGHT", "그린라이트 (데이비드 아인혼)"),
    (921669, "ICAHN", "칼 아이칸"), (1697748, "ARK", "ARK 인베스트 (캐시 우드)"), (1166559, "GATES", "게이츠 재단 신탁"),
    (1112520, "AKRE", "아크레 캐피탈"), (1569205, "FUNDSMITH", "펀드스미스 (테리 스미스)"), (1096343, "MARKEL", "마켈"),
    (1709323, "HIMALAYA", "히말라야 캐피탈 (리루)"), (1034524, "POLEN", "폴렌 캐피탈"), (1791786, "ELLIOTT", "엘리엇"),
    (102909, "VANGUARD", "뱅가드"), (93751, "STATE STREET", "스테이트 스트리트"), (315066, "FMR", "피델리티 (FMR)"),
    (1364742, "BLACKROCK", "블랙록"), (2012383, "BLACKROCK", "블랙록 (신규 법인)"),
]
NS = re.compile(r"\{.*?\}")


def _strip(root):
    for e in root.iter():
        e.tag = NS.sub("", e.tag)
    return root


def parse_infotable(xml):
    root = _strip(ET.fromstring(xml))
    out = []
    for it in root.iter("infoTable"):
        g = lambda p: (it.findtext(p) or "").strip()
        out.append({"issuer": g("nameOfIssuer"), "cls": g("titleOfClass"), "cusip": g("cusip").upper(),
                    "value": float(g("value") or 0), "shares": float(g("shrsOrPrnAmt/sshPrnamt") or 0),
                    "sh_type": g("shrsOrPrnAmt/sshPrnamtType"), "put_call": g("putCall") or None})
    return out


def cusip_map():
    """SPDR ETF 보유 파일의 식별번호(CUSIP)와 티커 — 최근 파일들에서 모음"""
    m = {}
    for p in sorted((DATA / "etf" / "holdings").glob("*.parquet"))[-5:]:
        h = pd.read_parquet(p)
        if "cusip" not in h:
            continue
        h = h[h.cusip.astype(str).str.fullmatch(r"[0-9A-Z]{9}") & h.holding.notna()]
        m.update(dict(zip(h.cusip, h.holding.astype(str).str.replace(".", "-", regex=False))))
    return m


def run(limit=0, full=False, **_):
    R = Run("f13")
    http = sec_http()
    mgrs = MANAGERS[:limit] if limit else MANAGERS
    done = read(F_DIR / "holdings.parquet")
    done_acc = set(done.accession) if not done.empty else set()
    ok_m, bad_m, rows, n_fil = [], [], [], 0
    quarters = 8 if (full or done.empty) else 2
    for cik, key, ko in mgrs:
        try:
            j = http.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
        except Exception as e:
            bad_m.append(f"{ko}: 조회 실패"); continue
        name = j.get("name", "")
        if key not in name.upper():
            bad_m.append(f"{ko}: 이름 불일치({name[:30]})"); continue
        rc = pd.DataFrame(j["filings"]["recent"])
        f = rc[rc.form.isin(["13F-HR", "13F-HR/A"])].copy()
        if f.empty:
            bad_m.append(f"{ko}: 13F 없음"); continue
        f["reportDate"] = pd.to_datetime(f.reportDate, errors="coerce")
        f = f.sort_values(["reportDate", "filingDate"]).groupby("reportDate").tail(1)   # 분기별 마지막(정정 반영)
        f = f.sort_values("reportDate").tail(quarters)
        ok_m.append({"manager_cik": cik, "manager": name, "manager_ko": ko})
        for r in f.itertuples():
            if r.accessionNumber in done_acc:
                continue
            acc = r.accessionNumber.replace("-", "")
            try:
                idx = http.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json").json()
                files = [x["name"] for x in idx["directory"]["item"] if x["name"].lower().endswith(".xml")]
                info = next((x for x in files if "info" in x.lower()), None) or next((x for x in files if x.lower() != "primary_doc.xml"), None)
                if not info:
                    raise RuntimeError("정보표 XML 없음")
                hold = parse_infotable(http.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{info}").content)
            except Exception as e:
                R.warning(f"{ko} {r.reportDate.date()}: {str(e)[:50]}"); continue
            # 2023년 이전 제출분은 단위가 천 달러
            mult = 1000 if pd.Timestamp(r.filingDate) < pd.Timestamp("2023-01-03") else 1
            for h in hold:
                rows.append({"manager_cik": cik, "manager": name, "period": r.reportDate, "filed": pd.Timestamp(r.filingDate),
                             "accession": r.accessionNumber, "cusip": h["cusip"], "issuer": h["issuer"], "cls": h["cls"],
                             "value_usd": h["value"] * mult, "shares": h["shares"], "sh_type": h["sh_type"], "put_call": h["put_call"]})
            n_fil += 1
        log(f"  {ko}: 완료")
    if ok_m:
        write(F_DIR / "managers.parquet", pd.DataFrame(ok_m))
    if rows:
        D = pd.DataFrame(rows)
        # 티커 매핑: 우리 ETF 보유 파일에 CUSIP이 있으면 사용, 없으면 발행사명 ↔ SEC 회사명 대조
        U = universe.load("stock")
        nm = U.assign(k=U["name"].astype(str).str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True).str.replace(r"\b(INC|CORP|CORPORATION|CO|LTD|PLC|HOLDINGS|GROUP|THE|CLASS [A-C]|COM|NEW)\b", "", regex=True).str.split().str.join(" "))
        key = D.issuer.str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True).str.replace(r"\b(INC|CORP|CORPORATION|CO|LTD|PLC|HOLDINGS|GROUP|THE|CLASS [A-C]|COM|NEW)\b", "", regex=True).str.split().str.join(" ")
        cm = cusip_map()
        D["ticker"] = D.cusip.map(cm).fillna(key.map(dict(zip(nm.k, nm.ticker))))
        R.set(cusip_map_size=len(cm))
        upsert(F_DIR / "holdings.parquet", D, ["accession", "cusip", "put_call", "cls"], sort=["period", "manager_cik"])
    H = read(F_DIR / "holdings.parquet")
    if bad_m:
        R.warning(f"건너뛴 기관 {len(bad_m)}곳: " + "; ".join(bad_m[:8]))
    if not H.empty:
        last = H[H.period == H.period.max()]
        mapped = (last.ticker.notna() * last.value_usd).sum() / max(last.value_usd.sum(), 1)
        R.set(latest_period=str(pd.Timestamp(H.period.max()).date()), positions_latest=len(last),
              ticker_mapped_by_value=f"{mapped*100:.0f}%")
    R.set(managers_ok=len(ok_m), managers_skipped=len(bad_m), filings_new=n_fil, rows_new=len(rows), http=http.stats())
    return R.done()
