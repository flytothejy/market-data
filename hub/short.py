"""FINRA 일별 공매도 거래량 (Reg SHO, 장외 보고분 합산 파일)

출처: https://cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt  (미 동부 18시까지 게시)
형식: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market  + 마지막 줄 건수
저장: data/hub/short/volume/YYYY.parquet   date, ticker, short_vol, short_exempt, total_vol
※ FINRA 보고분(장외·TRF)만 집계한 값이라 거래소 전체 거래량과 다름 — '공매도 비중' 추이로 씀
※ 공매도 잔고(월 2회)는 profile 수집기에서 받음
"""
import io, datetime as dt
import pandas as pd

from .core import DATA, Http, Run, log, upsert, read
from . import universe

V_DIR = DATA / "short" / "volume"
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt"
VENUE_URL = "https://cdn.finra.org/equity/regsho/daily/{v}shvol{d:%Y%m%d}.txt"
CNMS_START = dt.date(2018, 8, 1)          # 그 전에는 통합 파일이 없어 장외 보고처별 파일을 합산 (2009-08~)
VENUES = ["FNSQ", "FNYX", "FNRA", "FNQC"]


def parse(txt):
    df = pd.read_csv(io.StringIO(txt), sep="|", dtype={"Symbol": str})
    df = df[df["Symbol"].notna() & df["Date"].astype(str).str.fullmatch(r"\d{8}")]
    return pd.DataFrame({"date": pd.to_datetime(df["Date"].astype(str), format="%Y%m%d"),
                         "ticker": df["Symbol"].str.strip().str.upper().str.replace(r"[./ ]", "-", regex=True),
                         "short_vol": pd.to_numeric(df["ShortVolume"], errors="coerce"),
                         "short_exempt": pd.to_numeric(df.get("ShortExemptVolume"), errors="coerce"),
                         "total_vol": pd.to_numeric(df["TotalVolume"], errors="coerce")})


def run(limit=0, days=None, full=False, **_):
    R = Run("short_volume")
    U = universe.load()
    keep = set(U.ticker)
    have = sorted(V_DIR.glob("*.parquet"))
    last = None
    if have:
        last = read(have[-1]).date.max()
    days = days or (365 if full or last is None else 10)
    http = Http(rate=4)
    try:
        from zoneinfo import ZoneInfo
        ny = dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                   # Windows에 시간대 정보가 없을 때
        ny = dt.datetime.utcnow() - dt.timedelta(hours=5)
    today = ny.date() if ny.hour >= 18 else ny.date() - dt.timedelta(days=1)   # 18시(동부) 이후 게시
    dates = [today - dt.timedelta(days=k) for k in range(days, -1, -1)]
    dates = [d for d in dates if d.weekday() < 5]
    if limit:
        dates = dates[-limit:]
    def one(d, h):
        urls = [URL.format(d=d)] if d >= CNMS_START else [VENUE_URL.format(v=v, d=d) for v in VENUES]
        fr = []
        for u in urls:
            r = h.get(u, ok404=True)
            if r is None or not r.text.strip():
                continue                 # 휴장일 또는 아직 게시 전
            try:
                df = parse(r.text)
            except Exception:
                continue
            fr.append(df[df.ticker.isin(keep)])
        if not fr:
            return None
        df = pd.concat(fr, ignore_index=True)
        return df.groupby(["date", "ticker"], as_index=False)[["short_vol", "short_exempt", "total_vol"]].sum() if len(fr) > 1 else df

    got, frames = [], []
    if len(dates) > 60:                  # 과거분 한꺼번에 받기 (예: --days 6000 → 2010년부터)
        from concurrent.futures import ThreadPoolExecutor
        import threading
        local = threading.local()
        def job(d):
            if not hasattr(local, "h"):
                local.h = Http(rate=4)
            return d, one(d, local.h)
        with ThreadPoolExecutor(6) as ex:
            for d, df in ex.map(job, dates):
                if df is not None:
                    frames.append(df); got.append(d)
    else:
        for d in dates:
            df = one(d, http)
            if df is not None:
                frames.append(df); got.append(d)
    if not frames:
        R.warning("치명: 받은 파일이 없음")
        return R.done(ok=False)
    A = pd.concat(frames, ignore_index=True)
    for y, g in A.groupby(A.date.dt.year):
        upsert(V_DIR / f"{y}.parquet", g, ["date", "ticker"])
    cov = A[A.date == A.date.max()].ticker.nunique()
    R.set(days_fetched=len(got), first=str(min(got)), latest=str(max(got)), rows_new=len(A),
          tickers_latest_day=f"{cov}/{len(keep)}",
          median_short_ratio=f"{(A.short_vol/A.total_vol).median()*100:.0f}%", http=http.stats())
    if cov < len(keep):
        miss = sorted(keep - set(A[A.date == A.date.max()].ticker))
        R.warning(f"최근일 파일에 없는 종목 {len(miss)}개: {', '.join(miss[:15])}")
    return R.done()
