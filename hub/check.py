"""매일 이상값 점검 — 화면에 나가는 데이터(site/api/v1)를 사람이 보기 전에 한 번 더 확인

  python -m hub run check        (daily·close 묶음의 build 다음에 자동 실행)

점검 3단계
  1) 신선도: 가격 기준일이 마지막 거래일인지, 컨센서스가 너무 오래되지 않았는지        → 치명
  2) 커버리지: 핵심 지표가 채워진 종목 수가 직전 점검보다 크게 줄었는지                 → 10% 넘게 줄면 치명, 3% 넘으면 주의
  3) 종목별 이상값: 있을 수 없는 값(범위 밖) + 하루 사이 설명 안 되는 변화(주식 수·매출 급변)
     → 새로 생긴 것만 알림 (매일 같은 종목이 반복 알림되지 않게). 전체 목록은 _check/flags.parquet에 쌓음

결과: _status/check.json (텔레그램 알림은 notify가), _check/prev.json (다음 비교용 스냅샷)
"""
import json
import pandas as pd

from .core import DATA, Run, log, upsert, now_utc

SITE = DATA / "site" / "api" / "v1"
CHK = DATA / "_check"

# NYSE 휴장일 (조기 폐장은 거래일로 봄)
HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
}

# 커버리지를 지켜볼 핵심 지표 (화면 카테고리마다 대표 1~2개)
COVER = ["px", "mcap", "r1d", "c_n", "c_upside", "c_chg90", "rev", "rev_g", "om", "eps", "pe", "sv", "si", "g13", "nw7", "rf_new", "d200"]

# 있을 수 없는(또는 거의 확실히 계산 오류인) 값 — (필드, 설명, 조건 함수). 매출이 작은 회사의 극단값은 정상일 수 있어 매출 1억 달러 이상만 보는 것도 있음
BIG = lambda d: d.rev.fillna(0) >= 1e8
RULES = [
    ("px", "종가 0 이하", lambda d: d.px <= 0),
    ("mcap", "시가총액 0 이하", lambda d: d.mcap <= 0),
    ("r1d", "하루 ±50% 넘는 움직임", lambda d: d.r1d.abs() > 0.5),
    ("gm", "매출총이익률 -100%~100% 밖", lambda d: BIG(d) & ((d.gm > 1.0001) | (d.gm < -1))),
    ("om", "영업이익률 -300% 아래", lambda d: BIG(d) & (d.om < -3)),
    ("nm", "순이익률 ±300% 밖", lambda d: BIG(d) & (d.nm.abs() > 3)),
    ("rev_g", "매출 성장 1000% 넘음", lambda d: BIG(d) & (d.rev_g > 10)),
    ("pb", "PBR 1000배 넘음", lambda d: d.pb > 1000),
    ("ps", "PSR 500배 넘음", lambda d: BIG(d) & (d.ps > 500)),
    ("pe", "PER 0.5배 미만", lambda d: d.pe < 0.5),
    ("dy", "배당수익률 25% 넘음", lambda d: d.dy > 0.25),
    ("si", "공매도 잔고 60% 넘음", lambda d: d.si > 0.6),
    ("c_upside", "목표가 여력 +300% 넘거나 -80% 아래", lambda d: (d.c_upside > 3) | (d.c_upside < -0.8)),
    ("c_fpe", "선행 PER 0.5배 미만", lambda d: d.c_fpe < 0.5),
    ("roe", "ROE ±500% 밖", lambda d: BIG(d) & (d.roe.abs() > 5)),
]


def expected_day(asof_now=None):
    """지금(UTC) 기준 이미 마감한 마지막 미국 거래일 (휴장일 반영)"""
    ny = (asof_now or pd.Timestamp.now(tz="UTC")).tz_convert("America/New_York")
    d = ny.normalize().tz_localize(None)
    if ny.hour * 60 + ny.minute < 16 * 60 + 15:
        d -= pd.Timedelta(days=1)
    while d.weekday() >= 5 or d.strftime("%Y-%m-%d") in HOLIDAYS:
        d -= pd.Timedelta(days=1)
    return d


def trading_days_between(a, b):
    """a < 날짜 <= b 인 거래일 수"""
    days = pd.bdate_range(a + pd.Timedelta(days=1), b)
    return sum(1 for d in days if d.strftime("%Y-%m-%d") not in HOLIDAYS)


def _short(tks, n=8):
    tks = list(tks)
    return ", ".join(tks[:n]) + (f" 외 {len(tks) - n}개" if len(tks) > n else "")


def run(limit=0, **_):
    R = Run("check")
    p = SITE / "free" / "universe.json"
    if not p.exists():
        R.warning("치명: 화면용 데이터(universe.json)가 없음")
        return R.done(ok=False)
    U = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(U["rows"])
    S = df[df.k == "stock"].set_index("t")
    for c in set(COVER + [r[0] for r in RULES] + ["rev", "px", "mcap"]):
        if c not in S:
            S[c] = float("nan")
        S[c] = pd.to_numeric(S[c], errors="coerce")
    today = now_utc().strftime("%Y-%m-%d")

    prev = {}
    pp = CHK / "prev.json"
    if pp.exists():
        try:
            prev = json.loads(pp.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    # 1) 신선도
    exp = expected_day()
    asof = pd.Timestamp(U.get("asof") or "1900-01-01")
    lag = trading_days_between(asof, exp) if asof < exp else 0
    R.set(price_asof=str(asof.date()), expected=str(exp.date()), stocks=len(S))
    if lag:
        R.warning(f"치명: 가격 기준일 {asof:%Y-%m-%d} — 마지막 거래일 {exp:%Y-%m-%d}보다 {lag}거래일 늦음")
    c_asof = pd.Timestamp(U.get("consensus_asof") or "1900-01-01")
    c_lag = trading_days_between(c_asof, exp) if c_asof < exp else 0
    if c_lag >= 2:
        R.warning(f"{'치명: ' if c_lag >= 3 else ''}컨센서스 기준일 {c_asof:%Y-%m-%d} — {c_lag}거래일 늦음")
    meta = SITE / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        for src, r in (m.get("sources") or {}).items():
            if src in ("check",):
                continue
            age = (now_utc() - pd.Timestamp(r["finished_utc"]).to_pydatetime()).days if r.get("finished_utc") else 99
            limit_days = 9 if src in ("profile", "f13") else 4
            if age > limit_days:
                R.warning(f"{src} 수집이 {age}일째 안 됨 (마지막 {r['finished_utc'][:10]})")

    # 2) 커버리지
    cov = {c: int(S[c].notna().sum()) for c in COVER}
    cov["_stocks"] = len(S)
    R.set(coverage=" ".join(f"{c}={cov[c]}" for c in ("px", "c_n", "rev", "sv", "g13")))
    pc = prev.get("coverage") or {}
    drops = []
    for c, n in cov.items():
        o = pc.get(c)
        if o and o >= 50 and n < o * 0.97:
            drops.append((c, o, n, 1 - n / o))
    if drops:
        drops.sort(key=lambda x: -x[3])
        worst = drops[0][3]
        R.warning(f"{'치명: ' if worst > 0.10 else ''}채워진 종목 수 감소: " +
                  ", ".join(f"{c} {o}→{n}(-{d*100:.0f}%)" for c, o, n, d in drops[:6]))

    # 3) 종목별 이상값
    flags = []
    for f, desc, fn in RULES:
        try:
            hit = S.index[fn(S).fillna(False).astype(bool)]
        except Exception as e:
            log(f"  규칙 {f} 건너뜀: {e}")
            continue
        for t in hit:
            flags.append({"ticker": t, "field": f, "rule": desc, "value": float(S.at[t, f])})
    # 하루 사이 설명 안 되는 변화 (직전 스냅샷 대비)
    ps = prev.get("snap") or {}
    if ps:
        P = pd.DataFrame(ps).T.reindex(S.index)
        sh_now = S.mcap / S.px
        sh_prev = P["mcap"] / P["px"]
        r = sh_now / sh_prev
        for t in S.index[(r > 1.5) | (r < 0.67)]:
            flags.append({"ticker": t, "field": "shares", "rule": "주식 수(시총÷주가)가 직전 점검 대비 50% 넘게 변함", "value": float(r[t])})
        rr = S.rev / P["rev"]
        for t in S.index[BIG(S) & ((rr > 1.6) | (rr < 0.6))]:
            flags.append({"ticker": t, "field": "rev", "rule": "매출(TTM)이 직전 점검 대비 40% 넘게 변함", "value": float(rr[t])})
        gone = [t for t in P.index if t in S.index and pd.notna(P.at[t, "px"]) and pd.isna(S.at[t, "px"])]
        for t in gone:
            flags.append({"ticker": t, "field": "px", "rule": "어제 있던 가격이 사라짐", "value": float("nan")})
    F = pd.DataFrame(flags, columns=["ticker", "field", "rule", "value"])
    old = set(prev.get("flagged") or [])
    key = (F.ticker + ":" + F.field) if len(F) else pd.Series(dtype=str)
    new = F[~key.isin(old)] if len(F) else F
    R.set(flags=len(F), new_flags=len(new))
    if len(new):
        for rule, g in new.groupby("rule", sort=False):
            R.warning(f"새 이상값 · {rule}: " + _short(f"{r.ticker}({r.value:.3g})" if pd.notna(r.value) else r.ticker for r in g.itertuples()))
    if len(F):
        upsert(CHK / "flags.parquet", F.assign(date=pd.Timestamp(today), new=~key.isin(old)), ["date", "ticker", "field"])

    snap_cols = ["px", "mcap", "rev"]
    snap = {t: {c: (None if pd.isna(S.at[t, c]) else float(S.at[t, c])) for c in snap_cols} for t in S.index}
    CHK.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps({"at": now_utc().isoformat(timespec="seconds"), "coverage": cov, "snap": snap,
                              "flagged": sorted(set(key))}, ensure_ascii=False), encoding="utf-8")
    return R.done()
