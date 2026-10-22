"""후보함 알림 엔진 — 매일 아침 묶음 (daily 묶음의 check 다음에 실행)

  python -m hub run alerts

1) 이벤트 감지 (전 종목, 어제 상태와 비교해 '바뀐 것'만)
   - er_d1   실적 발표 하루 전 (다음 거래일이 발표일)
   - er_res  실적 발표 뒤 주가 반응 (er.hist에 새 발표가 생김)
   - w:<k>   종목 점검표에 새로 생긴 경고 (최근 20일 안에 같은 경고가 없었을 때만 — 경계선에서 들락날락하는 소음 막기)
   - ins     임원 장내 매수 (최근 내부자 매수일이 새로 생김, 합계 5만 달러 이상)
2) 구독자(텔레그램 연결된 후보함)별로 묶어 메시지 한 통 → Cloudflare Worker(/internal/send)가 텔레그램으로 전달
   - 목적이 '그냥 관찰'인 종목은 검증된 신호·실적만
   - 같은 이벤트는 한 번만 (_alerts/state.json의 sent)
환경변수: ALERT_API (Worker 주소), ALERT_KEY (Worker와 같은 비밀값), SITE_URL — 없으면 감지·기록만 하고 보내지 않음
첫 실행은 기준만 잡고 '바뀐 것' 알림은 보내지 않음 (전 종목 경고가 한꺼번에 '새 경고'로 나가지 않게)
"""
import html, json, math, os
from datetime import date, datetime, timedelta

from .core import DATA, Run, log, now_utc
from .check import HOLIDAYS

SITE = DATA / "site" / "api" / "v1"
ST = DATA / "_alerts" / "state.json"
SITE_URL = os.environ.get("SITE_URL", "https://flytothejy.github.io/market-data").rstrip("/") + "/hub"
QUIET_DAYS = 20
PURPOSE_KO = {"hold": "보유 중", "consider": "살까 고민", "watch": "그냥 관찰"}
P_ORDER = {"hold": 0, "consider": 1, "": 2, "watch": 3}
WD = "월화수목금토일"

# ---- 종목 점검표의 경고 규칙 (web/assets/ui.js checklist()와 같은 기준 — 바꿀 땐 둘 다)
LENS = {
    "eps": ("EPS 전망", 0.3, lambda r: r.get("c_chg90") if r.get("c_chg90") is not None and (r.get("c_n") or 0) >= 3 else None),
    "rev": ("매출 가속", 0.3, lambda r: r["rev_qg"] - r["rev_g"] if r.get("rev_qg") is not None and r.get("rev_g") is not None else None),
    "guru": ("유명 투자자", 5, lambda r: r.get("g13_chg")),
    "insider": ("내부자", None, lambda r: _ins_y(r)),
    "short": ("공매도", 0.08, lambda r: -r["sv_chg60"] if r.get("sv_chg60") is not None else None),
}


def _ins_y(r):
    n = (r.get("ib") or 0) - (r.get("is") or 0)
    if not n:
        return None
    return math.copysign(max(0.05, min(1, (math.log10(abs(n)) - 4) / 4.5)), n)


def _num(v):
    return v if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else None


def pct(v, d=None):
    if v is None:
        return "-"
    d = d if d is not None else (1 if abs(v) < 0.1 else 0)
    return f"{'+' if v > 0 else ''}{v * 100:.{d}f}%"


def pp(v):
    return f"{'+' if v > 0 else ''}{v * 100:.1f}%p"


def usd(v):
    v = abs(v)
    return f"${v / 1e8:,.1f}억" if v >= 1e8 else f"${v / 1e4:,.0f}만" if v >= 1e4 else f"${v:,.0f}"


def warns(r, sec_med):
    """지금 켜져 있는 경고 {키: (제목, 설명, 검증 여부)}"""
    w = {}
    br = []
    r1m = r.get("r1m")
    for k, (nm, mx, f) in LENS.items():
        y = f(r)
        if y is None or r1m is None:
            continue
        yc = y if mx is None else max(-1, min(1, y / mx))
        if yc < -0.03 and r1m > 0.003:
            br.append(nm)
    if br:
        w["br"] = ("주가는 오르는데 신호는 꺾임", f"티커맵 오른쪽 아래: {', '.join(br)} (1개월 주가 {pct(r1m)})", True)
    if r.get("c_chg90") is not None and (r.get("c_n") or 0) >= 3 and r["c_chg90"] < -0.03:
        w["eps"] = ("이익 전망 하향 중", f"내년 EPS 전망 90일 {pct(r['c_chg90'])} · 30일 상향 {int(r.get('c_up') or 0)} / 하향 {int(r.get('c_dn') or 0)}", False)
    if r.get("rev_qg") is not None and r.get("rev_g") is not None and r["rev_qg"] - r["rev_g"] < -0.05:
        w["rev"] = ("매출 성장 느려지는 중", f"최근 분기 {pct(r['rev_qg'])} vs 4개 분기 {pct(r['rev_g'])}", False)
    if r.get("om_chg") is not None and r.get("om") is not None and r["om_chg"] < -0.03:
        w["om"] = ("이익률 악화", f"영업이익률 {r['om'] * 100:.1f}% (1년 전보다 {pp(r['om_chg'])})", False)
    if (r.get("ib") or 0) < 1e5 and r.get("is") and r.get("mcap") and r["is"] / r["mcap"] > 0.005:
        w["ins"] = ("내부자 매도 많음", f"최근 90일 매도 {usd(r['is'])} (시가총액의 {r['is'] / r['mcap'] * 100:.1f}%)", False)
    if r.get("g13_chg") is not None and r["g13_chg"] <= -2:
        w["guru"] = ("유명 투자자 매도 우위", f"순증 {int(r['g13_chg'])}곳 (13F, 분기 말 기준)", False)
    sv, si = r.get("sv_chg60"), r.get("si") or 0
    if sv is not None and (sv > 0.03 or si > 0.15):
        w["short"] = ("공매도 늘어남", f"거래 비중 60일 {pp(sv)}" + (f" · 공매도 잔고 {si * 100:.1f}%" if si else ""), False)
    med = sec_med.get(r.get("sec"))
    if med and (r.get("c_fpe") or 0) > 0 and r["c_fpe"] / med > 1.5:
        w["val"] = ("업종보다 비쌈", f"선행 PER {r['c_fpe']:.1f}배 · 업종 중간값 {med:.1f}배", False)
    if r.get("d200") is not None and r["d200"] < -0.1:
        w["trend"] = ("200일선 아래로", f"200일 평균 대비 {pct(r['d200'])}", False)
    return w


def next_trading(d):
    d = d + timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in HOLIDAYS:
        d += timedelta(days=1)
    return d


def kday(s):
    d = date.fromisoformat(s)
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def stock_json(t):
    try:
        return json.loads((SITE / "free" / "stock" / f"{t}.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def detect(U, prev, init):
    """전 종목 이벤트 {티커: [ {k, kind, title, desc, v(검증), ord} ]} + 오늘 상태"""
    rows = [r for r in U["rows"] if r.get("k") == "stock" or r.get("k") is None]
    rows = [{k: _num(v) if isinstance(v, float) else v for k, v in r.items()} for r in rows]
    asof = U["asof"]
    nxt = next_trading(date.fromisoformat(asof)).isoformat()
    by_sec = {}
    for r in rows:
        if (r.get("c_fpe") or 0) > 0:
            by_sec.setdefault(r.get("sec"), []).append(r["c_fpe"])
    sec_med = {s: sorted(v)[len(v) // 2] for s, v in by_sec.items() if len(v) >= 8}
    cut = (date.fromisoformat(asof) - timedelta(days=QUIET_DAYS)).isoformat()
    ev, state = {}, {}
    for r in rows:
        t = r["t"]
        p = prev.get(t, {})
        s = {"w": dict(p.get("w", {})), "ib_last": r.get("ib_last") if r.get("ib_last") not in (None, "NaT") else p.get("ib_last")}
        out = []
        # 실적 하루 전
        if r.get("c_next") == nxt:
            after = (r.get("c_when") or "").endswith("후")
            kst = kday((date.fromisoformat(nxt) + timedelta(days=1)).isoformat()) + " 새벽" if after else kday(nxt) + " 밤"
            extra = " · ".join(x for x in [f"옵션 예상 변동 ±{r['er_imp'] * 100:.1f}%" if r.get("er_imp") else "",
                                           f"최근 8번 평균 ±{r['er_avg'] * 100:.1f}%" if r.get("er_avg") else ""] if x)
            out.append({"k": f"er_d1:{nxt}", "kind": "er", "ord": 1, "title": f"실적 발표 임박 — 미국 {kday(nxt)} {r.get('c_when') or ''}".strip(),
                        "desc": f"한국 시간 {kst}" + (f" · {extra}" if extra else "")})
        # 실적 뒤 주가 반응 + 내부자 매수는 종목 파일에서 (후보함에 있을 만한 종목만 읽으면 되지만 단순하게 필요할 때만)
        need_stock = (r.get("er_avg") is not None) or s["ib_last"] != p.get("ib_last")
        sj = None
        er_last = p.get("er_last")
        if need_stock:
            sj = stock_json(t)
            hist = (sj.get("er") or {}).get("hist") or []
            if hist:
                s["er_last"] = hist[-1][0]
                if not init and er_last and hist[-1][0] > er_last and hist[-1][0] >= (date.fromisoformat(asof) - timedelta(days=5)).isoformat():
                    d0, mv = hist[-1]
                    avg = r.get("er_avg")
                    sur = r.get("c_surp")
                    big = avg and abs(mv) > 1.5 * avg
                    out.append({"k": f"er_res:{d0}", "kind": "er", "ord": 0, "v": False,
                                "title": f"실적 발표 뒤 주가 {pct(mv)}" + (" — 평소보다 크게 움직임" if big else ""),
                                "desc": f"{kday(d0)} 발표 · 발표 전날 → 다음 날 종가" + (f" · 최근 평균 ±{avg * 100:.1f}%" if avg else "")
                                        + (f" · 직전 분기 EPS 예상 대비 {pct(sur)}" if sur is not None and (U.get('consensus_asof') or '') > d0 else "")})
            elif er_last:
                s["er_last"] = er_last
        elif er_last:
            s["er_last"] = er_last
        # 임원 장내 매수
        if not init and s["ib_last"] and s["ib_last"] != p.get("ib_last") and (p.get("ib_last") or "") < s["ib_last"]:
            sj = sj or stock_json(t)
            buys = [x for x in sj.get("insider") or [] if x.get("code") == "P" and x.get("d", "") > (p.get("ib_last") or "")]
            tot = sum(x.get("v") or 0 for x in buys)
            if tot >= 5e4:
                top = max(buys, key=lambda x: x.get("v") or 0)
                who = f"{top.get('title') or ''} {top.get('who') or ''}".strip()
                out.append({"k": f"ins:{s['ib_last']}", "kind": "ins", "ord": 2, "v": True, "title": f"임원 장내 매수 {usd(tot)}",
                            "desc": f"{who} 외 {len(buys) - 1}건" if len(buys) > 1 else f"{who} · {top.get('d', '')[5:].replace('-', '/')}"})
        # 점검표 새 경고
        now_w = warns(r, sec_med)
        for k, (title, desc, v) in now_w.items():
            last = p.get("w", {}).get(k)
            if not init and (last is None or last < cut):
                out.append({"k": f"w:{k}:{asof}", "kind": "warn", "ord": 0 if v else 3, "v": v, "title": f"새 경고: {title}", "desc": desc})
            s["w"][k] = asof
        s["w"] = {k: d for k, d in s["w"].items() if d >= cut}
        state[t] = s
        if out:
            ev[t] = out
    return ev, state, {r["t"]: r for r in rows}


def message(asof, items, ev, R):
    """한 사용자의 아침 묶음 (텔레그램 HTML). 보낼 게 없으면 None"""
    blocks, keys = [], []
    def rank(it):
        e = ev.get(it["t"], [])
        return (0 if any(x.get("v") or x["kind"] == "er" for x in e) else 1, P_ORDER.get(it.get("purpose") or "", 2), it["t"])
    for it in sorted(items, key=rank):
        e = ev.get(it["t"])
        if not e:
            continue
        if it.get("purpose") == "watch":                     # 그냥 관찰: 검증된 신호·실적만
            e = [x for x in e if x.get("v") or x["kind"] == "er"]
        e = [x for x in e if x["k"] not in it.get("_sent", ())]
        if not e:
            continue
        r = R.get(it["t"], {})
        ret = (r.get("px") / it["px"] - 1) if it.get("px") and r.get("px") else None
        head = f"<b>{html.escape(it['t'])}</b> {html.escape(r.get('ko') or r.get('n') or '')}"
        sub = " · ".join(x for x in [PURPOSE_KO.get(it.get("purpose") or "", ""), f"담은 뒤 {pct(ret)}" if ret is not None else ""] if x)
        lines = [head + (f"  <i>{html.escape(sub)}</i>" if sub else "")]
        icon = {"er": "📅", "ins": "👤", "warn": "⚠️"}
        for x in sorted(e, key=lambda x: x["ord"]):
            lines.append(f"{icon.get(x['kind'], '·')} {html.escape(x['title'])}{' [검증]' if x.get('v') else ''}\n    <i>{html.escape(x['desc'])}</i>")
            keys.append(f"{it['t']}|{x['k']}")
        lines.append(f'<a href="{SITE_URL}/s/{it["t"]}/">종목 화면 →</a>')
        blocks.append("\n".join(lines))
    if not blocks:
        return None, []
    top = f"<b>티커맵 아침 브리핑</b> · 미국 {kday(asof)} 종가 기준\n후보함 {len(items)}종목 중 {len(blocks)}종목에 새 소식"
    foot = (f'<a href="{SITE_URL}/watch.html">후보함 열기</a> · 알림 멈춤 /끄기\n'
            "점수나 추천이 아니라 확인할 거리예요. [검증] = 16년 백테스트에서 이후 성과와 관련이 확인된 신호")
    return [top] + blocks + [foot], keys


def split(parts, limit=3900):
    """텔레그램 한 통 4096자 제한 — 종목 단위로 나눔"""
    msgs, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 2 > limit:
            msgs.append(cur)
            cur = ""
        cur = (cur + "\n\n" + p) if cur else p[:limit]
    if cur:
        msgs.append(cur)
    return msgs


def _api(path, body=None):
    import requests
    base, key = os.environ["ALERT_API"].rstrip("/"), os.environ["ALERT_KEY"]
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = (requests.post(base + path, headers=h, data=json.dumps(body), timeout=60) if body is not None
         else requests.get(base + path, headers=h, timeout=60))
    r.raise_for_status()
    return r.json()


def run(limit=0, full=False, **_):
    R = Run("alerts")
    U = json.loads((SITE / "free" / "universe.json").read_text(encoding="utf-8"))
    old = json.loads(ST.read_text(encoding="utf-8")) if ST.exists() else {}
    init = not old.get("tickers")
    if old.get("asof") == U["asof"] and not full:
        R.set(skip=f"이미 {U['asof']} 기준으로 처리함")
        log("alerts: 같은 기준일 — 건너뜀 (--full로 강제)")
        return R.done()
    ev, state, rows = detect(U, old.get("tickers", {}), init)
    n_ev = sum(len(v) for v in ev.values())
    R.set(asof=U["asof"], init=init, tickers_with_events=len(ev), events=n_ev,
          kinds={k: sum(1 for v in ev.values() for x in v if x["kind"] == k) for k in ("er", "warn", "ins")})
    sent = old.get("sent", {})
    cut = (now_utc() - timedelta(days=40)).date().isoformat()
    sent = {u: {k: d for k, d in m.items() if d >= cut} for u, m in sent.items()}
    n_msg = n_user = 0
    if os.environ.get("ALERT_API") and os.environ.get("ALERT_KEY"):
        try:
            subs = _api("/internal/subs")["users"]
            out = []
            for u in subs:
                mine = sent.get(u["uid"], {})
                for it in u["items"]:
                    it["_sent"] = {k.split("|", 1)[1] for k in mine if k.startswith(it["t"] + "|")}
                parts, keys = message(U["asof"], u["items"], ev, rows)
                if not parts:
                    continue
                for m in split(parts):
                    out.append({"uid": u["uid"], "text": m, "_keys": keys})
            ok_users = set()
            for i in range(0, len(out), 15):
                chunk = out[i:i + 15]
                res = _api("/internal/send", {"msgs": [{"uid": m["uid"], "text": m["text"]} for m in chunk]})["results"]
                for m, rr in zip(chunk, res):
                    if rr.get("ok"):
                        n_msg += 1
                        ok_users.add(m["uid"])
                        sent.setdefault(m["uid"], {}).update({k: U["asof"] for k in m["_keys"]})
                    elif rr.get("why") != "unlinked":
                        R.warning(f"발송 실패 {m['uid'][:4]}…: {rr.get('why')}")
            n_user = len(ok_users)
            R.set(subscribers=len(subs), sent_users=n_user, sent_msgs=n_msg)
        except Exception as e:
            R.warning(f"알림 발송 실패: {e}")
    else:
        R.set(send="ALERT_API 없음 — 감지만")
    ST.parent.mkdir(parents=True, exist_ok=True)
    tmp = ST.with_suffix(".tmp")
    tmp.write_text(json.dumps({"asof": U["asof"], "at": now_utc().isoformat(timespec="seconds"), "tickers": state, "sent": sent}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ST)
    (ST.parent / "last_events.json").write_text(json.dumps(ev, ensure_ascii=False, indent=0), encoding="utf-8")
    log(f"alerts: 이벤트 {n_ev}건 ({len(ev)}종목){' · 첫 실행이라 기준만' if init else ''} · 보냄 {n_user}명 {n_msg}통")
    return R.done()
