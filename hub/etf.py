"""ETF 구성 종목 — 운용사 일별 파일(가능한 곳) + yfinance 상위 보유·섹터 비중(전체 ETF)

저장
  data/hub/etf/holdings/YYYY-MM-DD.parquet  etf, source, holding, name, weight(%), shares, value
  data/hub/etf/funds.parquet                ETF별 섹터 비중·자산 구성·운용 정보(최신)
  data/hub/etf/sources.parquet              ETF별 마지막 성공 출처(운용사 / yfinance 상위 10)
운용사 파일은 형식이 바뀌면 깨질 수 있음 → 실패하면 yfinance 상위 보유로 자동 대체하고 점검표에 표시
"""
import io, json, datetime as dt
import pandas as pd
import yfinance as yf

from .core import DATA, Http, Run, log, read, upsert, write
from . import universe

E_DIR = DATA / "etf"
SSGA = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{t}.xlsx"
INVESCO = "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker={T}"
PROSHARES = "https://accounts.profunds.com/etfdata/ByFund/{T}-psdlyhld.csv"
DIREXION = "https://www.direxion.com/holdings/{T}.csv"
# iShares 상품 번호 (틀린 번호는 다른 펀드를 가리킬 수 있어, 파일 첫 줄 펀드명을 yfinance 이름과 대조)
ISHARES_ID = {"IVV": 239726, "IWB": 239707, "IWM": 239710, "IWF": 239706, "IWD": 239708, "IJH": 239763, "IJR": 239774,
              "EFA": 239623, "EEM": 239637, "IEFA": 244049, "IEMG": 244050, "ACWI": 239600, "AGG": 239458, "TLT": 239454,
              "IEF": 239456, "SHY": 239452, "LQD": 239566, "HYG": 239565, "TIP": 239467, "SHV": 239466, "EMB": 239572,
              "MUB": 239766, "GOVT": 239468, "SOXX": 239705, "IBB": 239699, "IGV": 239771, "ITA": 239502, "ITB": 239512,
              "EWJ": 239665, "EWY": 239681, "EWT": 239686, "EWZ": 239612, "EWG": 239650, "EWU": 239690, "INDA": 239659,
              "MCHI": 239619, "DGRO": 264623, "HDV": 239563, "DVY": 239500, "IAU": 239561, "SLV": 239855, "IBIT": 333011}
ISH_URL = "https://www.ishares.com/us/products/{pid}/x/latest-holdings.csv"
ARK = {"ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS", "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS",
       "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS"}
ARK_URL = "https://ark-funds.com/wp-content/uploads/funds-etf-csv/{f}.csv"


def _frame(df, etf, src, tcol, ncol, wcol, scol=None, vcol=None):
    out = pd.DataFrame({"etf": etf, "source": src,
                        "holding": df[tcol].astype(str).str.strip().str.upper() if tcol in df else None,
                        "name": df[ncol].astype(str).str.strip() if ncol in df else None,
                        "weight": pd.to_numeric(df[wcol].astype(str).str.replace("%", "").str.replace(",", ""), errors="coerce") if wcol in df else None,
                        "shares": pd.to_numeric(df[scol].astype(str).str.replace(",", ""), errors="coerce") if scol and scol in df else None,
                        "value": pd.to_numeric(df[vcol].astype(str).str.replace("[$,]", "", regex=True), errors="coerce") if vcol and vcol in df else None})
    if out.weight.notna().sum() == 0 and out.value.notna().sum() > 0:     # 비중 열이 비어 있으면 시장가치로 계산
        out["weight"] = out.value / out.value.abs().sum() * 100
    out.attrs["cols"] = list(map(str, df.columns))[:10]
    out = out[out.weight.notna()]
    return out


def _header_at(raw, key):
    for i in range(min(25, len(raw))):
        row = [str(x).strip() for x in raw.iloc[i].tolist()]
        if key in row:
            df = raw.iloc[i + 1:].copy()
            df.columns = row
            return df.dropna(how="all")
    raise RuntimeError(f"'{key}' 머리글 없음")


def ssga(http, t):
    raw = pd.read_excel(io.BytesIO(http.get(SSGA.format(t=t.lower())).content), header=None)
    df = _header_at(raw, "Ticker")
    return _frame(df, t, "ssga", "Ticker", "Name", "Weight", "Shares Held")


def invesco(http, t):
    df = pd.read_csv(io.StringIO(http.get(INVESCO.format(T=t), headers={"Accept": "text/csv,application/csv,text/plain,*/*",
                                                                      "Referer": "https://www.invesco.com/"}).text))
    w = next(c for c in df.columns if "weight" in c.lower())
    tc = next((c for c in df.columns if c.lower() in ("holding ticker", "ticker")), df.columns[1])
    nc = next((c for c in df.columns if "name" in c.lower()), tc)
    sc = next((c for c in df.columns if "shares" in c.lower()), None)
    vc = next((c for c in df.columns if "marketvalue" in c.lower().replace(" ", "")), None)
    return _frame(df, t, "invesco", tc, nc, w, sc, vc)


def proshares(http, t):
    txt = http.get(PROSHARES.format(T=t)).text
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if "Ticker" in l and ("Weight" in l or "Market Value" in l))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    w = next((c for c in df.columns if "weight" in c.lower()), None)
    if w is None:                      # 비중 열이 없으면 시장가치로 계산
        mv = next(c for c in df.columns if "market value" in c.lower())
        df["_w"] = pd.to_numeric(df[mv].astype(str).str.replace("[$,]", "", regex=True), errors="coerce")
        df["_w"] = df["_w"] / df["_w"].sum() * 100
        w = "_w"
    nc = next((c for c in df.columns if "description" in c.lower() or "name" in c.lower()), "Ticker")
    return _frame(df, t, "proshares", "Ticker", nc, w)


def direxion(http, t):
    txt = http.get(DIREXION.format(T=t)).text
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if "Ticker" in l or "StockTicker" in l)
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    tc = next(c for c in df.columns if "ticker" in c.lower())
    nc = next((c for c in df.columns if "description" in c.lower() or "name" in c.lower()), tc)
    mv = next((c for c in df.columns if "marketvalue" in c.lower().replace(" ", "")), None)
    if mv:
        df["_w"] = pd.to_numeric(df[mv].astype(str).str.replace("[$,]", "", regex=True), errors="coerce")
        df["_w"] = df["_w"] / df["_w"].abs().sum() * 100
    return _frame(df, t, "direxion", tc, nc, "_w", None, mv)


def ark(http, t):
    df = pd.read_csv(io.StringIO(http.get(ARK_URL.format(f=ARK[t])).text))
    w = next(c for c in df.columns if "weight" in c.lower())
    return _frame(df, t, "ark", "ticker", "company", w, "shares", next((c for c in df.columns if "market value" in c.lower()), None))


def ishares(http, t, expect_name=None):
    import difflib
    txt = http.get(ISH_URL.format(pid=ISHARES_ID[t])).text
    lines = txt.splitlines()
    fund = lines[0].strip().strip('"') if lines else ""
    if expect_name:
        sim = difflib.SequenceMatcher(None, fund.lower().replace("®", ""), str(expect_name).lower().replace("®", "")).ratio()
        if sim < 0.6:
            raise RuntimeError(f"펀드명 불일치: '{fund[:40]}' vs '{str(expect_name)[:40]}'")
    start = next(i for i, l in enumerate(lines) if l.startswith("Ticker,"))
    body = []
    for l in lines[start:]:
        if not l.strip() or l.startswith("\xa0") or l.startswith('"The content'):
            break
        body.append(l)
    df = pd.read_csv(io.StringIO("\n".join(body)), thousands=",")
    q = next((c for c in df.columns if c in ("Quantity", "Shares")), None)
    return _frame(df, t, "ishares", "Ticker", "Name", "Weight (%)", q, "Market Value")


def adapter(family, t):
    f = (family or "").lower()
    if t in ARK: return ark
    if t in ISHARES_ID: return ishares
    if "spdr" in f or "state street" in f: return ssga
    # Invesco는 자동 다운로드를 막음(406) → 상위 10개로 대체
    if "proshares" in f: return proshares
    if "direxion" in f: return direxion
    return None


def yf_fund(t):
    fd = yf.Ticker(t).funds_data
    top = fd.top_holdings
    hold = pd.DataFrame()
    if top is not None and len(top):
        top = top.reset_index()
        sym = top.columns[0]
        hold = pd.DataFrame({"etf": t, "source": "yf_top", "holding": top[sym].astype(str).str.upper(),
                             "name": top.get("Name"), "weight": pd.to_numeric(top.get("Holding Percent"), errors="coerce") * 100,
                             "shares": None, "value": None})
    info = {"etf": t}
    for k, fn in (("sectors", lambda: fd.sector_weightings), ("assets", lambda: fd.asset_classes),
                  ("overview", lambda: fd.fund_overview), ("operations", lambda: fd.fund_operations)):
        try:
            v = fn()
            if isinstance(v, pd.DataFrame):
                v = v.iloc[:, 0].to_dict() if v.shape[1] else {}
            info[k] = json.dumps({str(a): (float(b) if isinstance(b, (int, float)) else str(b)) for a, b in (v or {}).items()}, ensure_ascii=False)
        except Exception:
            info[k] = None
    return hold, info


def run(limit=0, **_):
    R = Run("etf")
    E = universe.load("etf")
    P = read(DATA / "profile" / "profile.parquet")
    fam = dict(zip(P.ticker, P.get("fundFamily", pd.Series(dtype=str)))) if not P.empty else {}
    lname = dict(zip(P.ticker, P.get("longName", pd.Series(dtype=str)))) if not P.empty else {}
    if limit:
        E = E.head(limit)
    http = Http(rate=2)
    H, infos, src, fail_issuer, fail_all = [], [], [], [], []
    for i, t in enumerate(E.ticker):
        full = None
        ad = adapter(fam.get(t), t)
        if ad:
            try:
                full = ad(http, t, lname.get(t)) if ad is ishares else ad(http, t)
                if full.empty or full.weight.sum() < 50:
                    raise RuntimeError(f"비중 합 {full.weight.sum():.0f}%, 열 {full.attrs.get('cols')}")
            except Exception as e:
                fail_issuer.append(f"{t}({ad.__name__}): {str(e)[:50]}")
                full = None
        try:
            top, info = yf_fund(t)
            infos.append(info)
        except Exception as e:
            top = pd.DataFrame()
        if full is not None:
            H.append(full); src.append((t, full.source.iloc[0], len(full)))
        elif not top.empty:
            H.append(top); src.append((t, "yf_top", len(top)))
        else:
            fail_all.append(t)
        if (i + 1) % 25 == 0:
            log(f"  ETF {i+1}/{len(E)}")
    today = dt.date.today().isoformat()
    if H:
        A = pd.concat(H, ignore_index=True).assign(date=today)
        write(E_DIR / "holdings" / f"{today}.parquet", A)
    if infos:
        F = pd.DataFrame(infos).assign(fetched=today)
        old = read(E_DIR / "funds.parquet")
        if not old.empty:
            F = pd.concat([old[~old.etf.isin(F.etf)], F], ignore_index=True)
        write(E_DIR / "funds.parquet", F)
    S = pd.DataFrame(src, columns=["etf", "source", "n"])
    if not S.empty:
        upsert(E_DIR / "sources.parquet", S.assign(date=today), ["etf"])
    if fail_issuer:
        R.warning(f"운용사 파일 실패 {len(fail_issuer)}개 → 상위 10개로 대체: " + "; ".join(fail_issuer[:6]))
    if fail_all:
        R.warning(f"구성 정보를 전혀 못 받은 ETF {len(fail_all)}개: {', '.join(fail_all[:15])}")
    by = S.groupby("source").etf.count().to_dict() if not S.empty else {}
    R.set(etfs=len(E), full_holdings=sum(v for k, v in by.items() if k != "yf_top"), top10_only=by.get("yf_top", 0),
          by_source=", ".join(f"{k} {v}" for k, v in by.items()), failed=len(fail_all),
          funds_info=len(infos), rows_new=int(sum(len(h) for h in H)), http=http.stats())
    return R.done()
