"""사건 알림 (연구 과제 2-2·2-5·2-6·2-7) — SEC 공시 목록에서 매일 찾음, 과거 통계는 spec 값 그대로

- 행동주의 13D: 원본 SC 13D / SCHEDULE 13D(/A 제외), 대상 회사 = 그 종목, 제출자 CIK가 행동주의 펀드 목록에 있음 (N4)
- 합병: 대상 확정 = 그 회사가 낸 SC 14D9/SC14D9C, 또는 SC TO-T/TO-C에서 SUBJECT COMPANY가 그 회사이고 FILED BY가 다른 회사
        PREM14A·DEFM14A·425 단독 = 중립 '합병 관련 공시'(통계 없음). DEFA14A는 정기 주총에도 쓰여 쓰지 않음
- 파산: 8-K 항목 1.03
- 주식분할: 가격 수집의 분할 기록(효력일)
제출자·대상은 공시 머리말(-index-headers.html)에서 읽고 data/hub/sec/headers.parquet에 저장해 다시 받지 않음
"""
import json, re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .core import DATA, log, read

SPEC = Path(__file__).resolve().parent / "spec"
HDR_P = DATA / "sec" / "headers.parquet"
F13D = {"SC 13D", "SCHEDULE 13D"}
TARGET_FORMS = {"SC 14D9", "SC14D9C", "SC TO-T", "SC TO-C"}
MERGER_REL = {"PREM14A", "DEFM14A", "425"}


def _spec():
    s = json.loads((SPEC / "tickermap_spec.json").read_text(encoding="utf-8"))
    return s.get("event_alert_stats_large", {}), s.get("event_alert_stats", {})


def activists():
    d = json.loads((SPEC / "activist_ciks.json").read_text(encoding="utf-8"))
    return {int(c): fund for fund, xs in d.items() for c, _ in xs}


def _parse_header(txt):
    """SEC-HEADER 글 → {subject: [cik], filer: [(cik, 이름)]}"""
    out = {"subject": [], "filer": []}
    for part in re.split(r"\n(?=(?:SUBJECT COMPANY|FILED BY|FILER):)", txt):
        head = part.split(":", 1)[0].strip()
        ciks = [int(x) for x in re.findall(r"CENTRAL INDEX KEY:\s*(\d+)", part)]
        names = re.findall(r"COMPANY CONFORMED NAME:\s*(.+)", part)
        if head == "SUBJECT COMPANY":
            out["subject"] += ciks
        elif head in ("FILED BY", "FILER"):
            out["filer"] += list(zip(ciks, [n.strip() for n in names] + [""] * len(ciks)))
    return out


def headers(rows, http):
    """[(cik, accession)] → {accession: {subject, filer}} (저장분 + 새로 받은 것)"""
    have = read(HDR_P)
    known = {r.accession: {"subject": json.loads(r.subject), "filer": [tuple(x) for x in json.loads(r.filer)]} for r in have.itertuples()} if len(have) else {}
    new = []
    for cik, acc in rows:
        if acc in known or http is None:
            continue
        a = acc.replace("-", "")
        try:
            r = http.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{acc}-index-headers.html", ok404=True)
            if r is None:
                continue
            h = _parse_header(re.sub(r"<[^>]+>", "", r.text))
            known[acc] = h
            new.append({"accession": acc, "subject": json.dumps(h["subject"]), "filer": json.dumps(h["filer"], ensure_ascii=False)})
        except Exception as e:
            log(f"  공시 머리말 실패 {acc}: {str(e)[:60]}")
    if new:
        HDR_P.parent.mkdir(parents=True, exist_ok=True)
        pd.concat([have, pd.DataFrame(new)], ignore_index=True).drop_duplicates("accession", keep="last").to_parquet(HDR_P, index=False)
    return known


def pct(v):
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v) * 100:.1f}%".replace(".0%", "%")


def scan(tickers, asof, days=5, http=None):
    """최근 며칠 안의 사건 {티커: [ {k, kind:'ev', title, desc, ord} ]} — tickers: {티커: cik}"""
    L, A = _spec()
    cut, end = pd.Timestamp(date.fromisoformat(asof) - timedelta(days=days)), pd.Timestamp(asof) + pd.Timedelta(days=1)
    by_cik = {int(c): t for t, c in tickers.items() if c}
    F = read(DATA / "sec" / "filings.parquet", columns=["cik", "ticker", "accession", "form", "filed", "items"])
    out = {}
    if len(F):
        fd = pd.to_datetime(F.filed)
        F = F[(fd >= cut) & (fd < end) & F.cik.isin(set(by_cik))]
        need = F[F.form.isin(F13D | TARGET_FORMS)]
        H = headers(list(zip(need.cik, need.accession)), http)
        act = activists()
        seen_rel = set()
        for r in F.sort_values("filed").itertuples():
            t, cik, f, d = by_cik[int(r.cik)], int(r.cik), r.form, str(pd.Timestamp(r.filed).date())
            ev = None
            if f in F13D:
                h = H.get(r.accession)
                if h and cik in h["subject"]:
                    fund = next((act[c] for c, _ in h["filer"] if c in act), None)
                    if fund:
                        s = L.get("activist_13d", {})
                        ev = {"k": f"ev13d:{r.accession}", "title": f"행동주의 펀드 {fund}, 지분 5% 이상 신고",
                              "desc": f"경영 관여 목적의 13D ({d}) · 과거 대형주 비슷한 공시 뒤 3일 평균 {pct(s['car_3d_mean'])}, 이후 1년 중앙값 {pct(s['post_1y_median'])}"}
            elif f in TARGET_FORMS:
                h = H.get(r.accession)
                if h:
                    filers = {c for c, _ in h["filer"]}
                    target = (f in ("SC 14D9", "SC14D9C") and (cik in h["subject"] or cik in filers)) or \
                             (f in ("SC TO-T", "SC TO-C") and cik in h["subject"] and cik not in filers)
                    if target:
                        s = L.get("merger_target", {})
                        what = "공개매수 대상 회사의 의견서" if f.startswith("SC 14D9") or f == "SC14D9C" else "이 회사를 대상으로 한 공개매수"
                        ev = {"k": f"evtgt:{r.accession}", "title": "피인수 대상 확정 공시",
                              "desc": f"{what} ({f}, {d}) · 과거 대형주 피인수 발표 3일 평균 {pct(s['car_3d_mean'])} (중앙값 {pct(s['car_3d_median'])})"}
            elif f in MERGER_REL and (t, d) not in seen_rel:
                seen_rel.add((t, d))
                ev = {"k": f"evrel:{t}:{d}", "title": "합병 관련 공시",
                      "desc": f"{f} ({d}) · 인수하는 쪽인지 인수되는 쪽인지는 공시 원문에서 확인하세요"}
            elif f == "8-K" and "1.03" in str(r.items or "").split(","):
                s = L.get("bankruptcy_8k_103_large_1y_before", {})
                ev = {"k": f"evbk:{r.accession}", "title": "파산 절차 관련 공시 (8-K 항목 1.03)",
                      "desc": f"{d} · 과거 대형주 파산 공시 뒤 3일 평균 {pct(s['car_3d_mean'])}, 공시 전 1년 평균 {pct(s['pre_1y_mean'])}"}
            if ev:
                out.setdefault(t, []).append({**ev, "kind": "ev", "ord": 0})
    # 주식분할 (효력일, 가격 수집 기록)
    AC = read(DATA / "prices" / "actions.parquet")
    if len(AC):
        ad = pd.to_datetime(AC.date)
        sp = AC[(ad >= cut) & (ad < end) & (AC.split > 0) & (AC.split != 1) & AC.ticker.isin(set(tickers))]
        # 분할다운 비율만 (3:2·2:1·10:1 등). 주식 배당(1.012)이나 분사 조정 같은 어정쩡한 값은 빼고
        nice = lambda x: abs(x * 2 - round(x * 2)) < 0.02 and x >= 1.4
        sp = sp[[nice(x) if x > 1 else nice(1 / x) for x in sp.split]]
        s = A.get("split", {})
        for r in sp.itertuples():
            d = str(pd.Timestamp(r.date).date())
            if r.split > 1:
                ev = {"k": f"evsp:{r.ticker}:{d}", "title": f"주식분할 {r.split:g}대 1 효력",
                      "desc": f"{d} · 과거 분할 효력일 3일 중앙값 {pct(s['effective_3d_median'])}, 이후 1년 중앙값 {pct(s['post_1y_median'])}"}
            else:
                ev = {"k": f"evsp:{r.ticker}:{d}", "title": f"주식 병합 {1 / r.split:g}주 → 1주 효력", "desc": d}
            out.setdefault(r.ticker, []).append({**ev, "kind": "ev", "ord": 1})
    return out
