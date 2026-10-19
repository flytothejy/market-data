"""10-K 본문 처리 — HTML→텍스트, 위험요인(Item 1A)·경영진 논의(Item 7) 분리, 텍스트 특성
PC 연구용 스크립트(data_ext/fetch_10k.py, text_features.py)의 계산을 그대로 옮김 → 예전 결과와 같은 값
외부 패키지 없음 (re, math, collections)
"""
import csv, html, math, random, re
from collections import Counter

# ---- HTML → 텍스트
RE_DROP = re.compile(r"(?is)<(script|style|ix:header|xbrli:context|head)[^>]*>.*?</\1>")
RE_HIDDEN = re.compile(r'(?is)<div[^>]*display:\s*none[^>]*>.*?</div>')
RE_BLOCK = re.compile(r"(?i)</?(p|div|br|tr|li|h[1-6]|table|section)[^>]*>")
RE_TAG = re.compile(r"(?s)<[^>]+>")


def to_text(raw):
    t = RE_DROP.sub(" ", raw)
    t = RE_HIDDEN.sub(" ", t)
    t = RE_BLOCK.sub("\n", t)
    t = RE_TAG.sub(" ", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def section(text, start_pat, end_pat, min_len=2000):
    """목차가 아닌 본문 섹션: 시작 후보 중 다음 종료 표시까지가 가장 긴 구간"""
    best = ""
    for m in re.finditer(start_pat, text):
        e = re.search(end_pat, text[m.end():])
        seg = text[m.start(): m.end() + (e.start() if e else min(len(text) - m.end(), 400000))]
        if len(seg) > len(best):
            best = seg
    return best if len(best) >= min_len else ""


RF_S = r"(?im)^\s*item\s*1a\s*[\.\:\-–—]?\s*risk\s+factors"
RF_E = r"(?im)^\s*item\s*(1b|2)\s*[\.\:\-–—]?\s*(unresolved|properties)"
MD_S = r"(?im)^\s*item\s*7\s*[\.\:\-–—]?\s*management.{0,5}s?\s+discussion"
MD_E = r"(?im)^\s*item\s*(7a|8)\s*[\.\:\-–—]?\s*(quantitative|financial\s+statements)"


def parse(raw):
    text = to_text(raw) if ("<html" in raw[:5000].lower() or "<div" in raw[:20000].lower()) else raw
    return dict(full=text, rf=section(text, RF_S, RF_E), mdna=section(text, MD_S, MD_E))


# ---- 특성
TOK = re.compile(r"[a-z][a-z\-']+")
SENT = re.compile(r"(?<=[\.\?\!])\s+(?=[A-Z])")
STOP = set("the of and to in a for or on by with as is be are that this our we from at an any its it not may which have has will such other these than been were their into under including".split())
LM, SYL, IDF = None, {}, None


def load_lm(path):
    neg, pos, unc, lit, syl = set(), set(), set(), set(), {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            w = r["Word"].lower()
            if r["Negative"] not in ("0", ""): neg.add(w)
            if r["Positive"] not in ("0", ""): pos.add(w)
            if r["Uncertainty"] not in ("0", ""): unc.add(w)
            if r["Litigious"] not in ("0", ""): lit.add(w)
            try:
                syl[w] = int(r["Syllables"])
            except Exception:
                pass
    return dict(neg=neg, pos=pos, unc=unc, lit=lit), syl


def init(idf, lm_path):
    global LM, SYL, IDF
    LM, SYL = load_lm(lm_path)
    IDF = idf


def toks(text):
    return [w for w in TOK.findall((text or "").lower()) if w not in STOP and len(w) > 1]


def tfidf(tokens):
    c = Counter(tokens)
    v = {w: (1 + math.log(n)) * IDF.get(w, IDF["__max__"]) for w, n in c.items()}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {w: x / norm for w, x in v.items()}


def cos(a, b):
    if not a or not b:
        return float("nan")
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def syllables(w):
    s = SYL.get(w)
    return s if s is not None else max(1, len(re.findall(r"[aeiouy]+", w)))


def fog(text):
    sents = [s for s in SENT.split(text) if len(s.split()) >= 3]
    if len(sents) < 10:
        return float("nan")
    words = TOK.findall(text.lower())
    if not words:
        return float("nan")
    asl = len(words) / len(sents)
    cx = sum(1 for w in words if syllables(w) >= 3) / len(words)
    return 0.4 * (asl + 100 * cx)


def rf_sents(text, cap=600):
    ss = [set(toks(s)) for s in SENT.split(text or "")]
    ss = [w for w in ss if len(w) >= 8]
    if len(ss) > cap:
        random.Random(7).shuffle(ss)
        ss = ss[:cap]
    return ss


def _best_overlap(w, prev, inv):
    cnt = Counter()
    for x in w:
        for i in inv.get(x, ()):
            cnt[i] += 1
    return max((inter / len(w | prev[i]) for i, inter in cnt.most_common(20)), default=0.0)


def _inv(prev):
    inv = {}
    for i, s in enumerate(prev):
        for w in s:
            inv.setdefault(w, []).append(i)
    return inv


def new_ratio(cur, prev):
    """올해 위험 문장 중 작년 어떤 문장과도 단어 자카드 0.5 미만인 비율"""
    if not cur or not prev:
        return float("nan")
    inv = _inv(prev)
    return sum(_best_overlap(s, prev, inv) < 0.5 for s in cur) / len(cur)


def new_sentences(cur_rf, prev_rf, cap=40):
    """새로 들어온 위험 문장 원문 (화면 표시용, 긴 순)"""
    split = lambda t: [s.strip() for s in SENT.split(t or "") if len(set(toks(s))) >= 8]
    cur, prev = split(cur_rf), split(prev_rf)
    if not cur or not prev:
        return []
    pv = [set(toks(s)) for s in prev]
    inv = _inv(pv)
    out = [s[:600] for s in cur if _best_overlap(set(toks(s)), pv, inv) < 0.5]
    out.sort(key=len, reverse=True)
    return out[:cap]


def lm_ratios(tokens):
    n = len(tokens) or 1
    c = Counter(tokens)
    f = lambda S: sum(v for w, v in c.items() if w in S) / n
    return f(LM["neg"]), f(LM["pos"]), f(LM["unc"]), f(LM["lit"])


def features(doc, prev=None):
    """문서 1건의 특성 (+직전 연도 문서가 있으면 비교 지표). doc: full, rf, mdna, filed, acc, form, report"""
    tf, tr, tm = toks(doc["full"]), toks(doc["rf"]), toks(doc["mdna"])
    mneg, mpos, munc, _ = lm_ratios(tm) if tm else (float("nan"),) * 4
    flit = lm_ratios(tf)[3]
    row = dict(filed=doc["filed"], acc=doc["acc"], form=doc["form"], report=doc.get("report", ""),
               n_full=len(tf), n_rf=len(tr), n_md=len(tm), md_neg=mneg, md_pos=mpos, md_unc=munc, full_lit=flit,
               md_fog=fog(doc["mdna"]) if doc["mdna"] else float("nan"))
    if prev is not None:
        pf, pr, pm = toks(prev["full"]), toks(prev["rf"]), toks(prev["mdna"])
        row.update(prev_acc=prev["acc"], prev_filed=prev["filed"],
                   sim_full=cos(tfidf(tf), tfidf(pf)),
                   sim_rf=cos(tfidf(tr), tfidf(pr)) if tr and pr else float("nan"),
                   sim_md=cos(tfidf(tm), tfidf(pm)) if tm and pm else float("nan"),
                   rf_new=new_ratio(rf_sents(doc["rf"]), rf_sents(prev["rf"])))
    return row
