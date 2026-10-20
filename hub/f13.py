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
# (CIK, 이름 확인용 키워드, 한국어 표시명, 종류)
#   guru  = 소수 종목에 집중하는 유명 투자자·행동주의 펀드 → '유명 투자자 보유 수'에 셈
#   fund  = 대형 헤지펀드·퀀트 (수천 종목) → 상세 화면에만
#   inst  = 대형 운용사 (지수형 포함, 거의 모든 종목 보유) → 상세 화면에만
MANAGERS = [
    (1067983, "BERKSHIRE", "버크셔 해서웨이 (워런 버핏)", "guru"), (1336528, "PERSHING", "퍼싱스퀘어 (빌 애크먼)", "guru"),
    (1649339, "SCION", "사이언 (마이클 버리)", "guru"), (1656456, "APPALOOSA", "아팔루사 (데이비드 테퍼)", "guru"),
    (1061768, "BAUPOST", "바우포스트 (세스 클라만)", "guru"), (1536411, "DUQUESNE", "듀케인 패밀리오피스 (드러켄밀러)", "guru"),
    (1040273, "THIRD POINT", "서드포인트 (댄 롭)", "guru"), (1167483, "TIGER GLOBAL", "타이거 글로벌 (체이스 콜먼)", "guru"),
    (1135730, "COATUE", "코투 매니지먼트 (필립 라퐁)", "guru"), (1029160, "SOROS", "소로스 펀드", "guru"),
    (1103804, "VIKING", "바이킹 글로벌 (안드레아스 할보르센)", "guru"), (1061165, "LONE PINE", "론파인 캐피탈 (스티븐 맨델)", "guru"),
    (1489933, "DME", "DME 캐피탈 (데이비드 아인혼, 옛 그린라이트)", "guru"), (921669, "ICAHN", "칼 아이칸", "guru"),
    (1697748, "ARK", "ARK 인베스트 (캐시 우드)", "guru"), (1166559, "GATES", "게이츠 재단 신탁", "guru"),
    (1112520, "AKRE", "아크레 캐피탈 (척 아크레)", "guru"), (1569205, "FUNDSMITH", "펀드스미스 (테리 스미스)", "guru"),
    (1096343, "MARKEL", "마켈 (토마스 게이너)", "guru"), (1709323, "HIMALAYA", "히말라야 캐피탈 (리루)", "guru"),
    (1034524, "POLEN", "폴렌 캐피탈", "guru"), (1791786, "ELLIOTT", "엘리엇 (폴 싱어)", "guru"),
    (1549575, "DALAL STREET", "달랄 스트리트 (모니시 파브라이)", "guru"), (860643, "GARDNER RUSSO", "가드너 루소 (톰 루소)", "guru"),
    (732905, "TWEEDY", "트위디 브라운", "guru"), (1720792, "RUANE", "루안 커니프 (세쿼이아 펀드)", "guru"),
    (1115373, "SEMPER AUGUSTUS", "셈퍼 아우구스투스 (크리스 블룸스트란)", "guru"), (1484150, "LINDSELL", "린셀 트레인 (닉 트레인)", "guru"),
    (1553733, "BRAVE WARRIOR", "브레이브 워리어 (글렌 그린버그)", "guru"), (1345471, "TRIAN", "트라이언 (넬슨 펠츠)", "guru"),
    (1418814, "VALUEACT", "밸류액트", "guru"), (1517137, "STARBOARD", "스타보드 밸류 (제프 스미스)", "guru"),
    (1798849, "DURABLE", "듀러블 캐피탈 (헨리 엘렌보겐)", "guru"), (1541617, "ALTIMETER", "알티미터 (브래드 거스트너)", "guru"),
    (949509, "OAKTREE", "오크트리 (하워드 막스)", "guru"), (934639, "MAVERICK", "매버릭 캐피탈", "guru"),
    (1350694, "BRIDGEWATER", "브리지워터 (레이 달리오)", "fund"), (1037389, "RENAISSANCE", "르네상스 테크놀로지", "fund"),
    (1423053, "CITADEL", "시타델 (켄 그리핀)", "fund"), (1273087, "MILLENNIUM", "밀레니엄", "fund"),
    (1179392, "TWO SIGMA", "투시그마", "fund"), (1009207, "SHAW", "D.E. 쇼", "fund"),
    (1603466, "POINT72", "포인트72 (스티브 코헨)", "fund"), (1167557, "AQR", "AQR (클리프 애스네스)", "fund"),
    (102909, "VANGUARD", "뱅가드", "inst"), (93751, "STATE STREET", "스테이트 스트리트", "inst"), (315066, "FMR", "피델리티 (FMR)", "inst"),
    (2012383, "BLACKROCK", "블랙록", "inst"), (200217, "DODGE", "다지 앤 콕스", "inst"),
]
QUARTERS = {"guru": 8, "fund": 4, "inst": 2}       # 처음 받을 분기 수 (대형 기관은 파일이 커서 짧게)
TOP_N = {"fund": 1500, "inst": 2000}               # 대형 기관은 평가액 상위 종목만 저장 (우리 종목 범위는 대부분 여기에 들어감)
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


def figi_map(cusips, R):
    """CUSIP → 티커 (OpenFIGI 무료 API, 키 없이 분당 25회·회당 10개). 결과는 f13/cusip.parquet에 쌓아 다시 묻지 않음"""
    import time, requests, os
    cp = F_DIR / "cusip.parquet"
    C = read(cp)
    known = set(C.cusip) if not C.empty else set()
    todo = [c for c in dict.fromkeys(cusips) if c and c not in known]
    key = os.environ.get("OPENFIGI_API_KEY")
    step, wait = (100, 0.26) if key else (10, 2.5)
    hdr = {"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": key} if key else {})}
    out, t_end = [], time.time() + (1500 if not key else 900)         # 한 번에 최대 25분 — 남은 건 다음 실행에서
    for k in range(0, len(todo), step):
        if time.time() > t_end:
            R.warning(f"CUSIP 매핑 시간 초과 — {len(todo) - k}개는 다음 실행에서"); break
        part = todo[k:k + step]
        for attempt in range(4):
            r = requests.post("https://api.openfigi.com/v3/mapping", headers=hdr, timeout=30,
                              json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in part])
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1)); continue
            break
        if r.status_code != 200:
            R.warning(f"OpenFIGI {r.status_code}"); break
        for c, res in zip(part, r.json()):
            d = (res.get("data") or [{}])[0]
            out.append({"cusip": c, "ticker": (d.get("ticker") or "").replace("/", "-") or None,
                        "figi_name": d.get("name"), "sec_type": d.get("securityType")})
        time.sleep(wait)
    if out:
        C = pd.concat([C, pd.DataFrame(out)], ignore_index=True) if not C.empty else pd.DataFrame(out)
        write(cp, C)
    R.set(cusip_cache=len(C), cusip_new=len(out))
    return dict(zip(C.cusip, C.ticker)) if not C.empty else {}


_STRIP = r"\b(INC|CORP|CORPORATION|CO|COS|LTD|LIMITED|PLC|HOLDINGS?|HLDGS?|GROUP|THE|CLASS [A-C]|CL [A-C]|COM|NEW|SA|S A|NV|N V|AG|A G|SE|LP|L P|TR|TRUST|INTL|INTERNATIONAL|DEL)\b"
_GENERIC = {"AMERICAN", "FIRST", "UNITED", "GENERAL", "NATIONAL", "BANK", "GLOBAL", "INTERNATIONAL", "CAPITAL", "WESTERN", "SOUTHERN",
            "NORTHERN", "EASTERN", "PACIFIC", "ATLANTIC", "ENERGY", "HEALTH", "DIGITAL", "REALTY", "PROPERTIES", "TECHNOLOGIES", "SERVICE",
            "SERVICES", "FINANCIAL", "INDUSTRIES", "BRANDS", "PARTNERS", "MEDICAL", "DATA", "NEW", "US", "U", "S", "ALLIED", "CENTRAL"}
ALIAS = {"EXXON MOBIL": "XOM"}          # 회사 재편으로 이름·CUSIP이 바뀐 경우


def _norm(x):
    return x.astype(str).str.upper().str.replace(r"[^A-Z0-9 ]", " ", regex=True).str.replace(_STRIP, " ", regex=True).str.split().str.join(" ")


def name_map(issuers, U):
    """발행사명 → 티커 (CUSIP으로 못 찾았을 때만): 정규화한 이름이 같거나, 첫 단어가 우리 종목 중 하나와만 맞을 때"""
    names = pd.concat([pd.DataFrame({"k": _norm(U["name"]), "t": U.ticker}), pd.DataFrame({"k": _norm(U["sec_name"].fillna("")), "t": U.ticker})])
    names = names[names.k.str.len() > 0]
    exact = dict(zip(names.k, names.t)) | ALIAS
    first = names.assign(f=names.k.str.split().str[0]).drop_duplicates(["f", "t"])
    first = first[~first.f.isin(_GENERIC) & (first.f.str.len() >= 4)]
    uniq = first.groupby("f").t.agg(lambda x: x.iloc[0] if x.nunique() == 1 else None).dropna().to_dict()
    k = _norm(pd.Series(list(issuers)))
    return {i: exact.get(n) or uniq.get(n.split()[0] if n else "") for i, n in zip(issuers, k)}


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
    # v2: 한 보고서 안에서 같은 종목이 여러 줄(하위 운용역별)로 나오는 걸 합산하도록 고침 → 예전 자료는 한 번 전부 다시 받음
    if not (F_DIR / ".v2").exists():
        done = done.iloc[0:0]
        full = True
    done_acc = set(done.accession) if not done.empty else set()
    ok_m, bad_m, rows, n_fil = [], [], [], 0
    done_mgr = set(done.manager_cik) if not done.empty else set()
    for cik, key, ko, kind in mgrs:
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
        f = f.sort_values("reportDate").tail(QUARTERS[kind] if (full or cik not in done_mgr) else 2)   # 새 기관은 과거 분기까지
        if f.reportDate.max() < pd.Timestamp.today() - pd.Timedelta(days=550):
            bad_m.append(f"{ko}: 최근 13F 없음"); continue
        ok_m.append({"manager_cik": cik, "manager": name, "manager_ko": ko, "kind": kind})
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
            if kind in TOP_N:                                  # 대형 기관: 옵션 제외, 평가액 상위만
                hold = sorted([h for h in hold if not h["put_call"]], key=lambda h: -h["value"])[:TOP_N[kind]]
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
        D = (D.groupby(["manager_cik", "accession", "cusip", "cls", "put_call"], dropna=False, sort=False)
               .agg({**{c: "first" for c in D.columns if c not in ("manager_cik", "accession", "cusip", "cls", "put_call", "value_usd", "shares")},
                     "value_usd": "sum", "shares": "sum"}).reset_index())
        # 티커 매핑: 우리 ETF 보유 파일에 CUSIP이 있으면 사용, 없으면 발행사명 ↔ SEC 회사명 대조
        cm = cusip_map()
        D["ticker"] = D.cusip.map(cm)
        fm = figi_map(D[D.ticker.isna()].sort_values("value_usd", ascending=False).cusip.tolist(), R)
        D["ticker"] = D.ticker.fillna(D.cusip.map(fm))
        R.set(cusip_map_size=len(cm))
        if not (F_DIR / ".v2").exists():
            write(F_DIR / "holdings.parquet", D.sort_values(["period", "manager_cik"]))
            (F_DIR / ".v2").write_text(dt.datetime.utcnow().isoformat())
        else:
            upsert(F_DIR / "holdings.parquet", D, ["accession", "cusip", "put_call", "cls"], sort=["period", "manager_cik"])
    H = read(F_DIR / "holdings.parquet")
    if not H.empty:
        # 2023년 이후에도 천 달러 단위로 내는 곳이 있음(바우포스트·듀케인 등) → 보고서별 주당 가격 중앙값이 비정상적으로 작으면 ×1000
        sh = H[(H.sh_type == "SH") & (H.shares > 0) & H.put_call.isna()]
        px = (sh.value_usd / sh.shares).groupby(sh.accession).median()
        small = set(px[px < 1.0].index)
        if small:
            H.loc[H.accession.isin(small), "value_usd"] *= 1000
            write(F_DIR / "holdings.parquet", H)
            R.set(unit_fixed_filings=len(small))
    if not H.empty:                                  # 이름 대조로 붙인 옛 티커도 CUSIP 기준으로 바로잡음
        fm = figi_map(H.sort_values("value_usd", ascending=False).cusip.tolist(), R)
        fixed = H.cusip.map(fm)
        miss = fixed.isna() & H.put_call.isna()                       # CUSIP으로 못 찾은 것만 이름으로 (우리 종목 범위 안에서)
        if miss.any():
            nmap = name_map(H.loc[miss, "issuer"].unique(), universe.load("stock"))
            fixed = fixed.where(~miss, H.issuer.map(nmap))
        n_fix = int((fixed.fillna("") != H.ticker.fillna("")).sum())
        if n_fix or H.ticker.isna().any():
            H["ticker"] = fixed
            write(F_DIR / "holdings.parquet", H)
        R.set(ticker_fixed=n_fix)
    if bad_m:
        R.warning(f"건너뛴 기관 {len(bad_m)}곳: " + "; ".join(bad_m[:8]))
    if not H.empty:
        last = H[H.period == H.period.max()]
        mapped = (last.ticker.notna() * last.value_usd).sum() / max(last.value_usd.sum(), 1)
        R.set(latest_period=str(pd.Timestamp(H.period.max()).date()), positions_latest=len(last),
              ticker_mapped_by_value=f"{mapped*100:.0f}%")
    R.set(managers_ok=len(ok_m), managers_skipped=len(bad_m), filings_new=n_fil, rows_new=len(rows), http=http.stats())
    return R.done()
