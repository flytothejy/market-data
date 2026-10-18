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


def parse(txt):
    df = pd.read_csv(io.StringIO(txt), sep="|", dtype={"Symbol": str})
    df = df[df["Symbol"].notna() & df["Date"].astype(str).str.fullmatch(r"\d{8}")]
    return pd.DataFrame({"date": pd.to_datetime(df["Date"].astype(str), format="%Y%m%d"),
                         "ticker": df["Symbol"].str.strip().str.upper().str.replace(r"[./ ]", "-", regex=True),
                         "short_vol": pd.to_numeric(df["ShortVolume"], errors="coerce"),
                         "short_exempt": pd.to_numeric(df.get("ShortExemptVolume"), errors="coerce"),
                         "total_vol": pd.to_numeric(df["TotalVolume"], errors="coerce")})


def run(limit=0, days=None, **_):
    R = Run("short_volume")
    U = universe.load()
    keep = set(U.ticker)
    have = sorted(V_DIR.glob("*.parquet"))
    last = None
    if have:
        last = read(have[-1]).date.max()
    days = days or (10 if last is not None else 365)
    http = Http(rate=4)
    today = dt.date.today()
    dates = [today - dt.timedelta(days=k) for k in range(days, -1, -1)]
    dates = [d for d in dates if d.weekday() < 5]
    if limit:
        dates = dates[-limit:]
    got, frames = [], []
    for d in dates:
        r = http.get(URL.format(d=d), ok404=True)
        if r is None or not r.text.strip():
            continue                     # 휴장일 또는 아직 게시 전
        df = parse(r.text)
        df = df[df.ticker.isin(keep)]
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
          median_short_ratio=f"{(A.short_vol/A.total_vol).median()*100:.0f}%")
    if cov < len(keep):
        miss = sorted(keep - set(A[A.date == A.date.max()].ticker))
        R.warning(f"최근일 파일에 없는 종목 {len(miss)}개: {', '.join(miss[:15])}")
    return R.done()
