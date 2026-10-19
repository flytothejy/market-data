"""화면용 지표 사전 — 이름·카테고리·형식·등급(free/pro). universe.json과 데이터 목록 페이지가 함께 씀
fmt: pct(0.123→12.3%), pctp(이미 % 단위), x(배수), usd, num, date, int, text
"""
CATS = {"cons": "컨센서스", "fin": "재무", "tech": "차트·수급", "doc": "공시·내부자", "news": "뉴스", "info": "기본"}

F = {
    # 기본
    "t": ("티커", "info", "text", "free"), "n": ("이름", "info", "text", "free"), "k": ("종류", "info", "text", "free"),
    "sec": ("업종", "info", "text", "free"), "ind": ("세부 업종", "info", "text", "free"),
    "mcap": ("시가총액", "info", "usd", "free"), "px": ("종가", "info", "usd", "free"),
    "idx": ("지수 편입", "info", "text", "free"), "cur": ("재무 통화", "info", "text", "free"),
    # 컨센서스 (S&P500부터, 확대 예정)
    "c_up": ("전망 상향(30일)", "cons", "int", "free"), "c_dn": ("전망 하향(30일)", "cons", "int", "free"),
    "c_ratio": ("순상향률", "cons", "pct", "free"), "c_n": ("애널리스트 수", "cons", "int", "free"),
    "c_chg90": ("90일 EPS 전망 변화", "cons", "pct", "free"), "c_upside": ("목표가 상승여력", "cons", "pct", "free"),
    "c_buy": ("매수 의견 비중", "cons", "pct", "free"), "c_eps_g": ("내년 EPS 성장(전망)", "cons", "pct", "free"),
    "c_rev_g": ("내년 매출 성장(전망)", "cons", "pct", "free"), "c_fpe": ("선행 PER", "cons", "x", "free"),
    "c_surp": ("최근 실적 서프라이즈", "cons", "pct", "free"), "c_beats": ("최근 4분기 상회 횟수", "cons", "int", "free"),
    "c_next": ("다음 실적 발표", "cons", "date", "free"),
    # 재무
    "rev": ("매출(TTM)", "fin", "usd", "free"), "rev_g": ("매출 성장(TTM)", "fin", "pct", "free"),
    "rev_qg": ("매출 성장(최근 분기)", "fin", "pct", "free"), "gm": ("매출총이익률", "fin", "pct", "free"),
    "om": ("영업이익률", "fin", "pct", "free"), "om_chg": ("영업이익률 변화(1년)", "fin", "pct", "free"),
    "nm": ("순이익률", "fin", "pct", "free"), "ni": ("순이익(TTM)", "fin", "usd", "free"),
    "ni_g": ("순이익 성장(TTM)", "fin", "pct", "free"), "eps": ("EPS(TTM)", "fin", "num", "free"),
    "fcf": ("잉여현금흐름(TTM)", "fin", "usd", "free"), "roe": ("ROE", "fin", "pct", "free"), "roa": ("ROA", "fin", "pct", "free"),
    "de": ("부채비율(장기부채/자본)", "fin", "x", "free"), "cr": ("유동비율", "fin", "x", "free"),
    "rnd": ("연구개발비 비중", "fin", "pct", "free"),
    "pe": ("PER(TTM)", "fin", "x", "free"), "ps": ("PSR", "fin", "x", "free"), "pb": ("PBR", "fin", "x", "free"),
    "fcfy": ("FCF 수익률", "fin", "pct", "free"), "dy": ("배당수익률", "fin", "pct", "free"),
    "shy": ("주주환원 수익률(배당+자사주)", "fin", "pct", "free"), "fq": ("최근 재무 기준일", "fin", "date", "free"),
    # 차트·수급
    "r1d": ("1일", "tech", "pct", "free"), "r1w": ("1주", "tech", "pct", "free"), "r1m": ("1개월", "tech", "pct", "free"),
    "r3m": ("3개월", "tech", "pct", "free"), "r6m": ("6개월", "tech", "pct", "free"), "r1y": ("1년", "tech", "pct", "free"),
    "rytd": ("연초 이후", "tech", "pct", "free"), "r12_1": ("12-1개월 모멘텀", "tech", "pct", "free"),
    "d50": ("50일선 대비", "tech", "pct", "free"), "d200": ("200일선 대비", "tech", "pct", "free"),
    "rsi": ("RSI(14)", "tech", "num", "free"), "hi52": ("52주 고가 대비", "tech", "pct", "free"),
    "lo52": ("52주 저가 대비", "tech", "pct", "free"), "vr": ("거래량 배수(20일/120일)", "tech", "x", "free"),
    "vol": ("변동성(60일, 연)", "tech", "pct", "free"), "gc": ("최근 골든크로스", "tech", "date", "free"),
    "sv": ("공매도 거래 비중(20일)", "tech", "pct", "free"), "sv_chg": ("공매도 비중 변화", "tech", "pct", "free"),
    "si": ("공매도 잔고(유통주식 대비)", "tech", "pct", "free"), "iv": ("내재변동성(30일)", "tech", "pct", "free"),
    "pcr": ("풋/콜 거래 비율", "tech", "x", "free"), "skew": ("옵션 왜곡(풋-콜 IV)", "tech", "pct", "free"),
    "etfn": ("편입 ETF 수(추적 대상)", "tech", "int", "free"), "g13": ("유명 투자자 보유 수", "tech", "int", "free"),
    "g13_chg": ("유명 투자자 순증 수(분기)", "tech", "int", "free"),
    # 공시·내부자
    "ib": ("내부자 매수 금액(90일)", "doc", "usd", "free"), "is": ("내부자 매도 금액(90일)", "doc", "usd", "free"),
    "ibn": ("내부자 매수 인원(90일)", "doc", "int", "free"), "ib_last": ("최근 내부자 매수일", "doc", "date", "free"),
    "k8": ("8-K 건수(30일)", "doc", "int", "free"), "k8_last": ("최근 8-K", "doc", "text", "free"),
    "k10": ("최근 10-K 제출일", "doc", "date", "free"), "rf_new": ("10-K 새 위험 문장 비율", "doc", "pct", "pro"),
    "rf_sim": ("10-K 위험요인 유사도", "doc", "num", "pro"), "md_unc": ("경영진 논의 불확실성 단어", "doc", "pct", "pro"),
    "f144": ("매도 예정 신고(Form 144, 30일)", "doc", "int", "free"), "g13d": ("대주주 지분 신고(13D/G, 90일)", "doc", "int", "free"),
    # 뉴스
    "nw7": ("뉴스 건수(7일)", "news", "int", "free"), "nw_last": ("최근 뉴스", "news", "text", "free"),
}
