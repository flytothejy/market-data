"""종목 목록: 러셀1000(IWB) + S&P500(IVV) + 나스닥100 + 다우30 + ETF 목록, SEC CIK 매핑, 편입 목록 일별 기록

저장
  data/hub/universe/universe.parquet        현재 대상 (ticker, kind, name, cik, 지수 편입 여부 …)
  data/hub/universe/members/YYYY-MM-DD.parquet  그날의 지수 구성 기록 (생존 편향 줄이기용)
"""
import io, datetime as dt
import pandas as pd

from .core import DATA, Http, Run, log, sec_http, write, read

U_DIR = DATA / "universe"
ISHARES = "https://www.ishares.com/us/products/{pid}/x/latest-holdings.csv"
FUNDS = {"r1000": 239707, "sp500": 239726}           # IWB, IVV
NASDAQ_NDX = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SSGA_DIA = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-dia.xlsx"
WIKI = {"ndx": ("https://en.wikipedia.org/wiki/Nasdaq-100", ("Ticker", "Symbol")),
        "dji": ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", ("Symbol", "Ticker"))}
ETF_LIST = __import__("pathlib").Path(__file__).with_name("etf_list.csv")


def ishares_holdings(http, pid):
    txt = http.get(ISHARES.format(pid=pid)).text
    lines = txt.splitlines()
    asof = next((l.split(",", 1)[1].strip().strip('"') for l in lines[:10] if l.lower().startswith("fund holdings as of")), "")
    start = next(i for i, l in enumerate(lines) if l.startswith("Ticker,"))
    body = []
    for l in lines[start:]:
        if not l.strip() or l.startswith("\xa0") or l.startswith('"The content'):
            break
        body.append(l)
    df = pd.read_csv(io.StringIO("\n".join(body)), thousands=",")
    df = df[df["Asset Class"].astype(str).str.lower().eq("equity")].copy()
    df["Weight (%)"] = pd.to_numeric(df["Weight (%)"], errors="coerce")
    return df, asof


def wiki_tickers(http, url, cols):
    html = http.get(url).text
    seen = []
    for t in pd.read_html(io.StringIO(html)):
        names = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        t.columns = names
        seen.append(f"{len(t)}행:{'/'.join(n[:12] for n in names[:5])}")
        for n in names:
            low = n.lower()
            if any(low.startswith(c.lower()) for c in cols) and 25 <= len(t) <= 130:
                s = t[n].astype(str).str.replace(r"^.*:\s*", "", regex=True).str.replace(r"\[.*?\]", "", regex=True).str.strip()
                s = [x for x in s if x and x != "nan" and len(x) <= 6]
                if len(s) >= 25:
                    return s
    raise RuntimeError(f"표를 찾지 못함 (표 {len(seen)}개: {'; '.join(seen)})")


import re
TICK_RE = re.compile(r"[A-Z][A-Z0-9.\-]{0,6}")


def ndx_nasdaq(http):
    j = http.get(NASDAQ_NDX, headers={"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com",
                                      "Referer": "https://www.nasdaq.com/"}).json()
    rows = (j.get("data") or {}).get("data", {}).get("rows") or []
    ts = [r["symbol"].strip().upper() for r in rows if r.get("symbol") and TICK_RE.fullmatch(r["symbol"].strip().upper())]
    if len(ts) < 90:
        raise RuntimeError(f"나스닥 API 종목 수 이상: {len(ts)}")
    return ts


def dji_ssga(http):
    raw = pd.read_excel(io.BytesIO(http.get(SSGA_DIA).content), header=None)
    hdr = next(i for i in range(min(15, len(raw))) if "Ticker" in raw.iloc[i].astype(str).tolist())
    df = raw.iloc[hdr + 1:].copy()
    df.columns = raw.iloc[hdr].astype(str)
    ts = [t for t in df["Ticker"].astype(str).str.strip().str.upper() if TICK_RE.fullmatch(t) and t != "CASH_USD"]
    if not 28 <= len(ts) <= 32:
        raise RuntimeError(f"DIA 구성 수 이상: {len(ts)}")
    return ts


def norm_ticker(t, known):
    t = " ".join(str(t).strip().upper().split())
    for c in (t, t.replace(" ", "-"), t.replace(".", "-"), t.replace("/", "-"), (t[:-1] + "-" + t[-1]) if len(t) > 2 else t):
        if c in known:
            return c
    return t.replace(".", "-")


def sec_tickers(http):
    j = http.get("https://www.sec.gov/files/company_tickers.json").json()
    df = pd.DataFrame(j.values()).rename(columns={"cik_str": "cik", "title": "sec_name"})
    df["ticker"] = df["ticker"].str.upper()
    return df.drop_duplicates("ticker")


def run(limit=0, **_):
    R = Run("universe")
    web = Http(rate=2)
    sec = sec_http()
    st = sec_tickers(sec)
    known = set(st.ticker)
    R.set(sec_tickers=len(st))

    members, rows = [], {}
    for idx, pid in FUNDS.items():
        try:
            h, asof = ishares_holdings(web, pid)
            for _, r in h.iterrows():
                raw = str(r["Ticker"]).strip().upper()
                if raw in ("-", "", "NAN"):
                    continue
                if raw.endswith(" WS") or "-R-W" in raw or raw.endswith(" RT"):
                    continue              # 워런트·권리 — 주식이 아님
                t = norm_ticker(raw, known)
                members.append({"index": idx, "ticker": t, "weight": r["Weight (%)"], "asof": asof})
                d = rows.setdefault(t, {"ticker": t, "kind": "stock", "name": r.get("Name"), "gics_sector": r.get("Sector")})
            R.set(**{f"{idx}_n": len(h), f"{idx}_asof": asof})
        except Exception as e:
            R.warning(f"치명: {idx} 구성 다운로드 실패 — {e}")
    primary = {"ndx": ndx_nasdaq, "dji": dji_ssga}
    for idx, (url, cols) in WIKI.items():
        try:
            try:
                ts = primary[idx](web)
            except Exception as e1:
                R.warning(f"{idx} 기본 출처 실패 → 위키백과로 대체: {str(e1)[:80]}")
                ts = wiki_tickers(web, url, cols)
            for t in ts:
                if not TICK_RE.fullmatch(str(t).strip().upper()):
                    continue
                t = norm_ticker(t, known)
                members.append({"index": idx, "ticker": t, "weight": None, "asof": dt.date.today().isoformat()})
                if t not in rows:
                    rows[t] = {"ticker": t, "kind": "stock", "name": None, "gics_sector": None}
            R.set(**{f"{idx}_n": len(ts)})
        except Exception as e:
            R.warning(f"{idx} 목록 실패 — {e}")

    M = pd.DataFrame(members)
    U = pd.DataFrame(rows.values())
    if not M.empty:
        flags = M.assign(v=True).pivot_table(index="ticker", columns="index", values="v", aggfunc="first")
        for c in ["r1000", "sp500", "ndx", "dji"]:
            U[f"in_{c}"] = U.ticker.map(flags[c] if c in flags else {}).fillna(False).astype(bool)
        U["r1000_weight"] = U.ticker.map(M[M["index"] == "r1000"].set_index("ticker")["weight"])
    # ETF
    etf = pd.read_csv(ETF_LIST)
    etf = etf.assign(kind="etf", name=None, gics_sector=None)
    U = pd.concat([U, etf[["ticker", "kind", "name", "gics_sector", "etf_group"]]], ignore_index=True)
    U = U.drop_duplicates("ticker", keep="first")
    U = U.merge(st[["ticker", "cik", "sec_name"]], on="ticker", how="left")
    U["name"] = U["name"].fillna(U["sec_name"])
    U["yf"] = U["ticker"]

    old = read(U_DIR / "universe.parquet")
    if U[U.kind == "stock"].shape[0] < 900:
        if not old.empty:
            R.warning(f"치명: 종목 수 {U[U.kind=='stock'].shape[0]}개로 비정상 — 이전 목록 유지")
            return R.done(ok=False)
    if limit:
        keep = list(U[U.kind == "stock"].sort_values("r1000_weight", ascending=False).ticker[:limit]) + list(U[U.kind == "etf"].ticker[: max(3, limit // 4)])
        U = U[U.ticker.isin(keep)]
    write(U_DIR / "universe.parquet", U)
    if not M.empty:
        write(U_DIR / "members" / f"{dt.date.today():%Y-%m-%d}.parquet", M)

    stocks = U[U.kind == "stock"]
    no_cik = stocks[stocks.cik.isna()].ticker.tolist()
    if no_cik:
        R.warning(f"SEC 목록에 없어 제외한 종목 {len(no_cik)}개 (상장폐지·비상장 전환 가능): {', '.join(no_cik[:15])}")
        U = U[~U.ticker.isin(no_cik)]
        write(U_DIR / "universe.parquet", U)
        stocks = U[U.kind == "stock"]
    if not old.empty and not limit:
        added = sorted(set(stocks.ticker) - set(old[old.kind == "stock"].ticker))
        removed = sorted(set(old[old.kind == "stock"].ticker) - set(stocks.ticker))
        R.set(added=", ".join(added[:20]) or "-", removed=", ".join(removed[:20]) or "-")
    R.set(stocks=len(stocks), etfs=int((U.kind == "etf").sum()), ndx_not_in_r1000=int((stocks.get("in_ndx", False) & ~stocks.get("in_r1000", False)).sum()),
          no_cik=len(no_cik), rows_new=len(U))
    return R.done()


def load(kind=None):
    U = read(U_DIR / "universe.parquet")
    if U.empty:
        raise SystemExit("종목 목록이 없습니다. 먼저  python -m hub run universe")
    return U if kind is None else U[U.kind == kind]
