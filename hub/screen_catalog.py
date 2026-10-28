"""AI 조건 검색용 필드 사전 — 문장을 조건으로 바꾸는 AI에게 주는 '쓸 수 있는 조건 목록'

  python -m hub.screen_catalog [universe.json 경로]   → hub/spec/screen_catalog.json

- 이름·카테고리·형식은 hub/fields.py(F)에서, 설명·같은 말·조건 형태는 아래 META에서 가져옴
- universe.json을 주면 종목별 값 분포(10%·중앙값·90%)와 값이 있는 비율을 함께 넣음 → AI가 '높다/낮다'의 기준을 잡는 데 씀
- AI는 이 목록에 있는 key만 쓸 수 있음. 없는 조건은 unsupported로 돌려줌 (features/ai-screen/README.md)

조건 형태(type)
  range  숫자 최소·최대        {"k":..., "min":x, "max":y}   (pct·ratio는 0.1 = 10%, usd는 달러)
  date   날짜가 최근 N일 안 / 앞으로 N일 안   {"k":..., "past_days":N} | {"k":..., "next_days":N}
  enum   정해진 값 중 하나      {"k":..., "in":[...]}
  flag   0/1 표시              {"k":..., "is":1}
  none   조건으로 못 씀(설명·텍스트) — 결과 표에만 보임
"""
import json, sys
from pathlib import Path

from .fields import F, CATS

OUT = Path(__file__).resolve().parent / "spec" / "screen_catalog.json"

SECTORS = {"Technology": "기술", "Industrials": "산업재", "Financial Services": "금융", "Consumer Cyclical": "경기소비재",
           "Healthcare": "헬스케어", "Real Estate": "부동산", "Consumer Defensive": "필수소비재", "Communication Services": "커뮤니케이션",
           "Basic Materials": "소재", "Utilities": "유틸리티", "Energy": "에너지"}
INDEXES = {"S&P500": "S&P 500", "NDX": "나스닥 100", "DOW": "다우 30", "R1000": "러셀 1000"}

# key: (type, 설명, 같은 말·자주 쓰는 표현, 주의)
META = {
    # 기본
    "t": ("none", "티커", "", ""), "n": ("none", "회사 영문 이름 (이름 검색은 query로)", "", ""),
    "k": ("none", "종류(stock/etf) — kind로 지정", "", ""),
    "sec": ("enum", "업종(11개, 영문 값)", "섹터, 업종, 기술주, 금융주, 헬스케어주, 에너지주", "값은 SECTORS의 영문 키"),
    "ind": ("none", "세부 업종(영문 자유 텍스트)", "", "조건으로 쓰지 않음 — 업종(sec)으로 대신"),
    "mcap": ("range", "시가총액(달러)", "시총, 대형주, 중소형주, 메가캡", "모호한 말 사전 참고"),
    "px": ("range", "최근 종가(달러)", "주가, 가격, 싼 주식", "'싼 주식'은 가격이 아니라 PER 등으로 묻는 경우가 많음 — 가정에 적기"),
    "idx": ("enum", "지수 편입(여러 개 가능)", "S&P500 종목, 나스닥100, 다우, 러셀1000", "값은 INDEXES의 키"),
    "s1": ("none", "한 줄 요약", "", ""), "cur": ("none", "재무 통화", "", ""),
    # 컨센서스
    "c_up": ("range", "최근 30일 EPS 전망을 올린 애널리스트 수", "전망 상향, 추정치 상향", ""),
    "c_dn": ("range", "최근 30일 EPS 전망을 내린 애널리스트 수", "전망 하향", ""),
    "c_ratio": ("range", "순상향률 = (상향-하향)/애널리스트 수 (최근 30일)", "리비전, 추정치 개선, 전망을 올린", "-1~1. '전망을 많이 올린' = min 0.3 (p90 근처), '올린 쪽이 더 많은' = min 0(초과)"),
    "c_n": ("range", "커버하는 애널리스트 수", "애널리스트 많은", ""),
    "c_chg90": ("range", "내년 EPS 전망이 90일 전보다 바뀐 비율", "이익 전망 상향, EPS 추정치 증가", ""),
    "c_upside": ("range", "애널리스트 평균 목표가 대비 상승 여력", "목표가 괴리, 업사이드", "목표가는 예측이므로 '목표가 대비 여력'이라고만 표현"),
    "c_buy": ("range", "매수 의견 비중", "매수 의견, 컨센서스 매수", ""),
    "c_eps_g": ("range", "내년 EPS 성장률(애널리스트 전망)", "이익 성장 전망", ""),
    "c_rev_g": ("range", "내년 매출 성장률(애널리스트 전망)", "매출 성장 전망", ""),
    "c_fpe": ("range", "선행 PER(내년 EPS 전망 기준, 배)", "포워드 PER, 선행 주가수익비율", ""),
    "c_surp": ("range", "가장 최근 분기 EPS 서프라이즈(실제/예상-1)", "어닝 서프라이즈, 예상 상회 폭", ""),
    "c_beats": ("range", "최근 4개 분기 중 EPS가 예상을 넘은 횟수(0~4)", "서프라이즈 연속, 4분기 연속 상회, 꾸준히 예상 상회", "'4분기 연속' = min 4"),
    "c_next": ("date", "다음 실적 발표 예정일", "이번 주 실적, 곧 실적 발표", "next_days 사용"),
    "c_when": ("enum", "다음 발표 시점", "장 전, 장 후", "값: '장 전' | '장 후'"),
    "er_avg": ("range", "최근 8번 실적 발표 다음 날 주가 변동 크기 평균(S&P 500 대비, 방향 없음)", "실적 때 크게 움직이는", ""),
    "er_d": ("date", "가장 최근 실적 발표일(최근 2주 안에 발표한 종목만 값 있음)", "최근 실적 발표한", "past_days 사용"),
    "er_eps_s": ("range", "최근 발표의 EPS 서프라이즈(최근 2주 발표 종목만)", "방금 발표한 실적 서프라이즈", ""),
    "er_rev_s": ("range", "최근 발표의 매출 서프라이즈(최근 2주 발표 종목만)", "매출 서프라이즈", ""),
    "er_mv": ("range", "최근 발표 다음 날 주가 반응(S&P 500 대비)", "실적 발표 후 주가", "지난 일이므로 방향 표시 가능"),
    "er_nq": ("range", "발표 뒤 다음 분기 매출 전망 변화", "가이던스 상향", ""),
    "er_imp": ("range", "옵션 시장이 예상하는 발표 전후 변동폭(발표 주간만)", "옵션 예상 변동", ""),
    "er_n": ("range", "지난 8번 평균 계산에 쓴 발표 횟수", "", "보통 조건으로 쓰지 않음"),
    "em_ind": ("range", "이번 시즌 같은 업종 회사들의 실적 반응 크기 평균", "", ""),
    "em_all": ("none", "em_ind가 업종 대신 전체 평균인지", "", ""),
    "ea_d": ("date", "가장 최근 실적 발표일(전 종목)", "지난달 실적 발표", "past_days 사용"),
    "c_est": ("none", "발표일이 추정치인지", "", ""), "c_rb": ("none", "", "", ""), "c_rh": ("none", "", "", ""), "c_rs": ("none", "", "", ""),
    # 재무
    "rev": ("range", "매출(최근 4개 분기 합, 달러)", "매출 규모", ""),
    "rev_g": ("range", "매출 성장률(최근 4개 분기 합, 1년 전 대비)", "매출 성장, 매출 증가", "'지속·연속 증가'는 rev_up_q를 씀"),
    "rev_qg": ("range", "최근 분기 매출 성장률(작년 같은 분기 대비)", "최근 분기 매출 증가, 매출 가속", "가속 = rev_qg > rev_g 이지만 두 필드 비교는 지원 안 함"),
    "gm": ("range", "매출총이익률", "마진, 총마진", ""), "om": ("range", "영업이익률", "영업마진, 흑자", "흑자 기업 = om>0 또는 ni>0"),
    "om_chg": ("range", "영업이익률 변화(1년, %p를 소수로)", "마진 개선", ""), "nm": ("range", "순이익률", "순마진", ""),
    "ni": ("range", "순이익(최근 4개 분기 합, 달러)", "흑자, 적자", "흑자 = min 0(초과), 적자 = max 0"),
    "ni_g": ("range", "순이익 성장률(1년)", "이익 증가, 순이익 증가", ""),
    "rev_up_q": ("range", "매출이 작년 같은 분기보다 늘어난 분기가 최근부터 몇 번 연속인지(0~12)", "매출 지속 증가, 매출 꾸준히 성장, 몇 분기 연속 매출 증가", "'지속 증가'는 min 4(1년 내내)로 보고 assumptions에 적기"),
    "ni_up_q": ("range", "순이익이 작년 같은 분기보다 늘어난 분기가 최근부터 몇 번 연속인지(0~12)", "이익 지속 증가, 순이익 꾸준히 증가", "'지속 증가'는 min 4"), "eps": ("range", "주당순이익(최근 4개 분기)", "EPS", ""),
    "fcf": ("range", "잉여현금흐름(최근 4개 분기, 달러)", "현금 창출, 현금 잘 버는, FCF 흑자", "'현금을 잘 버는' = fcf min 0(흑자) 또는 fcfy로 크기 조건"),
    "roe": ("range", "ROE", "자기자본이익률", ""), "roa": ("range", "ROA", "총자산이익률", ""),
    "de": ("range", "장기부채/자본(배)", "부채비율, 빚 적은", ""), "cr": ("range", "유동비율(배)", "단기 지급 능력", ""),
    "rnd": ("range", "매출 대비 연구개발비", "R&D 비중", ""),
    "pe": ("range", "PER(최근 4개 분기 이익 기준, 배)", "주가수익비율, 저PER, 싸다", "적자면 값 없음"),
    "ps": ("range", "PSR(배)", "주가매출비율", ""), "pb": ("range", "PBR(배)", "주가순자산비율", ""),
    "fcfy": ("range", "FCF 수익률(잉여현금흐름/시가총액)", "", ""), "dy": ("range", "배당수익률", "고배당, 배당주", "모호한 말 사전 참고"),
    "shy": ("range", "주주환원 수익률(배당+자사주 매입)", "주주환원, 자사주", ""), "fq": ("none", "최근 재무 기준일", "", ""),
    # 배당 점검 (연구 반영)
    "dvc_y": ("range", "분기 배당 회사의 배당수익률", "", "dy와 거의 같음 — dy 우선"),
    "dvc_m": ("enum", "매년 배당을 올려 온 달(1~12)", "11월에 배당 올리는, 배당 인상 시기", "값은 숫자 월 (예: {\"in\":[11]})"),
    "dvc_r": ("range", "같은 조건 회사의 과거 1년 내 배당 삭감 비율", "배당 삭감 위험 구간", "과거 집단 통계 — '위험'이라 단정하지 말고 '과거 삭감 비율 높은 구간'"),
    "dvc_v": ("flag", "변동 배당 회사(삭감 3회 이상)", "배당 들쭉날쭉", ""),
    "dvc_w": ("flag", "배당수익률 높고 지난 1년 시장 대비 −20% 이하", "", ""),
    # 위험·지수
    "dz": ("range", "부실 위험 등급 0 보통 · 1 주의 · 2 높음 · 3 매우 높음", "부실 위험, 재무 위험, 망할 위험", "'높음 이상' = min 2, '주의 이상' = min 1, '보통만' = max 0"),
    "dz_c": ("none", "부실 등급 근거 칩", "", ""),
    "ix_sp": ("range", "S&P 500 공개 요건 충족 비구성 회사 중 시가총액 순위(1=가장 큼)", "S&P 500 편입 후보, 문 앞", "'편입될 종목'이 아니라 '요건 충족 비구성'으로 표현"),
    "ix_nq": ("range", "나스닥 비금융 시가총액 순위", "나스닥 100 경계", ""),
    "ix_sp_chk": ("flag", "본사 확인 필요(설립지 해외)", "", ""),
    # 차트·수급
    "r1d": ("range", "1일 주가 변화", "오늘 오른, 어제", ""), "r1w": ("range", "1주 주가 변화", "이번 주", ""),
    "r1m": ("range", "1개월 주가 변화", "한 달", ""), "r3m": ("range", "3개월 주가 변화", "", ""),
    "r6m": ("range", "6개월 주가 변화", "", ""), "r1y": ("range", "1년 주가 변화", "1년 수익률", ""),
    "rytd": ("range", "연초 이후 주가 변화", "올해", ""), "r12_1": ("range", "12-1개월 모멘텀", "모멘텀", ""),
    "d50": ("range", "50일 이동평균 대비 위치", "50일선 위", "위 = min 0"), "d200": ("range", "200일 이동평균 대비 위치", "200일선 위, 장기 추세 위", "위 = min 0"),
    "rsi": ("range", "RSI(14)", "과매도, 과매수", "과매도 = max 30, 과매수 = min 70"),
    "hi52": ("range", "52주 고가 대비(0 = 고가, 음수)", "신고가, 고점 대비 하락", "신고가 부근 = min -0.03"),
    "lo52": ("range", "52주 저가 대비", "저점 대비", ""), "vr": ("range", "거래량 배수(20일/120일 평균)", "거래량 급증", ""),
    "vol": ("range", "변동성(60일, 연율)", "변동성 낮은, 안정적인", ""),
    "gc": ("date", "가장 최근 골든크로스(50일선이 200일선을 위로 뚫은 날)", "골든크로스", "'한 달 안' = past_days 30"),
    "sv": ("range", "공매도 거래 비중(20일 평균)", "공매도 많은", ""), "sv_chg": ("range", "공매도 거래 비중 변화(20일)", "", ""),
    "sv_chg60": ("range", "공매도 거래 비중 변화(60일)", "", ""), "si": ("range", "공매도 잔고(유통주식 대비)", "숏 잔고", ""),
    "iv": ("range", "내재변동성(30일, 상위 일부 종목만)", "", ""), "pcr": ("range", "풋/콜 거래 비율", "", ""),
    "skew": ("range", "옵션 왜곡(풋-콜 IV)", "", ""), "etfn": ("range", "이 종목을 담은 추적 ETF 수", "", ""),
    "g13": ("range", "보유 중인 유명 투자자 수(13F)", "버핏이 산, 유명 투자자 보유", "특정 투자자 이름 조건은 지원 안 함"),
    "g13_chg": ("range", "유명 투자자 순증 수(분기)", "", ""), "g13_new": ("range", "유명 투자자 신규 매수 수(분기)", "유명 투자자가 새로 산", ""),
    "g13_up": ("range", "유명 투자자 매수·늘림 수(분기)", "", ""), "f13_new": ("range", "추적 기관 전체 신규 매수 수", "", ""),
    "etf_add": ("range", "최근 약 30일 ETF 신규 편입 수", "", ""), "etf_drop": ("range", "최근 약 30일 ETF 편출 수", "", ""),
    "etf_wchg": ("range", "ETF 안 비중 변화 합", "", ""),
    # 공시·내부자
    "ib": ("range", "내부자 매수 금액(90일, 달러)", "내부자 매수, 임원이 산", ""), "is": ("range", "내부자 매도 금액(90일, 달러)", "내부자 매도", ""),
    "ibn": ("range", "내부자 매수 인원(90일)", "", ""), "ib_last": ("date", "최근 내부자 매수일", "", "past_days 사용"),
    "k8": ("range", "8-K 건수(30일)", "공시 많은", ""), "k8_last": ("none", "최근 8-K", "", ""),
    "k10": ("date", "최근 10-K 제출일", "", ""), "rf_new": ("range", "10-K 위험요인 중 작년에 없던 문장 비율", "위험요인 변화", ""),
    "rf_sim": ("range", "10-K 위험요인 작년 대비 유사도", "", ""), "md_unc": ("range", "경영진 논의 불확실성 단어 비율", "", ""),
    "f144": ("range", "매도 예정 신고 건수(30일)", "", ""), "g13d": ("range", "대주주 지분 신고 건수(90일)", "행동주의", ""),
    # 뉴스
    "nw7": ("range", "최근 7일 뉴스 건수", "화제, 뉴스 많은", ""), "nw_last": ("none", "최근 뉴스 제목", "", ""), "ko": ("none", "한국어 이름", "", ""),
}

# 모호한 말 → 기본 해석 (AI는 이 값을 쓰고, assumptions에 '이렇게 봤어요'를 적음. 사용자는 칩에서 고침)
VAGUE = {
    "대형주": {"k": "mcap", "min": 1e10}, "초대형주·메가캡": {"k": "mcap", "min": 2e11}, "중소형주": {"k": "mcap", "max": 1e10},
    "고배당": {"k": "dy", "min": 0.04}, "배당주": {"k": "dy", "min": 0.02},
    "고성장": {"k": "rev_g", "min": 0.2}, "흑자": {"k": "ni", "min": 0}, "적자": {"k": "ni", "max": 0},
    "저PER·싸다": {"k": "pe", "min": 0, "max": 15}, "빚 적은": {"k": "de", "max": 0.5},
    "신고가 부근": {"k": "hi52", "min": -0.03}, "과매도": {"k": "rsi", "max": 30}, "과매수": {"k": "rsi", "min": 70},
    "상승 추세": {"k": "d200", "min": 0}, "거래량 급증": {"k": "vr", "min": 1.5},
    "최근·요즘(날짜)": {"past_days": 30}, "곧·이번 주(발표)": {"next_days": 7},
}

# 조건으로 바꾸면 안 되는 요청 (추천·예측) — 정중히 조건 검색으로 돌려 말함
REFUSE = ["오를 종목", "살 만한 종목", "추천", "유망", "목표가 달성할", "떨어질 종목", "수익 날"]


def stats(path):
    u = json.loads(Path(path).read_text(encoding="utf-8"))
    R = [r for r in u["rows"] if r.get("k") == "stock"]
    out = {}
    for k in META:
        v = [r[k] for r in R if r.get(k) is not None]
        nums = sorted(x for x in v if isinstance(x, (int, float)) and not isinstance(x, bool))
        d = {"coverage": round(len(v) / len(R), 3)}
        if nums and len(nums) == len(v):
            d.update(p10=nums[len(nums) // 10], p50=nums[len(nums) // 2], p90=nums[len(nums) * 9 // 10])
        out[k] = d
    return out, u.get("asof")


def build(universe=None):
    st, asof = stats(universe) if universe else ({}, None)
    fields = []
    for k, (typ, desc, syn, note) in META.items():
        if typ == "none":
            continue
        lab, cat, fmt = (F[k][0], F[k][1], F[k][2]) if k in F else (desc.split("(")[0][:20], "etc", "num")
        unit = {"pct": "ratio (0.1 = 10%)", "usd": "USD", "x": "배", "int": "개수", "date": "YYYY-MM-DD", "num": "숫자"}.get(fmt, fmt)
        f = {"k": k, "label": lab, "cat": CATS.get(cat, cat), "type": typ, "unit": unit, "desc": desc}
        if syn:
            f["say"] = syn
        if note:
            f["note"] = note
        if k == "sec":
            f["values"] = SECTORS
        if k == "idx":
            f["values"] = INDEXES
        if k in st:
            f.update(st[k])
        fields.append(f)
    return {"version": asof or "", "fields": fields, "vague": VAGUE, "refuse": REFUSE,
            "output": "features/ai-screen/README.md §4 형식"}


if __name__ == "__main__":
    missing = [k for k in F if k not in META]
    if missing:
        print("META에 없는 필드:", missing)
    cat = build(sys.argv[1] if len(sys.argv) > 1 else None)
    OUT.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT} — 조건으로 쓸 수 있는 필드 {len(cat['fields'])}개")
