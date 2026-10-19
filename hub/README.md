# 종목 허브 데이터 수집기 (1차)

미국 주식 약 1,010종목(러셀1000 + 나스닥100 해외 ADR) + ETF 159개의 데이터를 모읍니다.
지금은 **PC에서 먼저 시험**하고, 안정되면 GitHub Actions로 옮깁니다. 수집 결과(`data/hub/`)는 시험 기간 동안 커밋하지 않습니다.

## 준비 (처음 한 번)

```bat
git clone https://github.com/flytothejy/market-data.git C:\project\market-data
cd C:\project\market-data
pip install -r requirements-hub.txt
setx SEC_CONTACT_EMAIL "본인이메일@example.com"
```
`setx` 후에는 **새 터미널**을 열어야 적용됩니다. 이미 받아 둔 저장소라면 `git pull`만 하면 됩니다.

## 실행

```bat
python -m hub run universe              :: 종목 목록 — 가장 먼저
python -m hub run phase1 --limit 20     :: 소량 시험 (종목 20개, Form 4 20건, 공매도 20일)
python -m hub run phase1                :: 전체
python -m hub status                    :: 마지막 점검표 다시 보기
```
수집기 하나만: `python -m hub run prices` (universe, prices, sec_filings, sec_insider, sec_financials, short_volume, profile)

## 수집기

| 이름 | 내용 | 출처 | 처음 실행 | 이후 |
|---|---|---|---|---|
| universe | 종목 목록, 지수 편입 기록, SEC CIK | iShares(IWB·IVV), 위키백과(나스닥100·다우), SEC | 수십 초 | 매일 |
| prices | 가격·수정종가·거래량·배당·분할 | yfinance | 2006년부터, 5~10분 | 최근 1개월 덮어쓰기 |
| sec_filings | 제출 목록(8-K 항목, 10-K/Q, 13D/G, 144, Form 4 …) | SEC submissions | 2~3분 | 매일 |
| sec_insider | Form 4 내부자 거래 | SEC 원문 XML | 최근 90일, 20~30분 (`--days 30`으로 줄일 수 있음) | 새 신고만 |
| sec_financials | XBRL 재무 핵심 항목 | SEC companyfacts | 1,010개 회사, 10~15분 | 새 10-K/10-Q 낸 회사만 |
| short_volume | 일별 공매도 거래량 | FINRA Reg SHO 파일 | 최근 1년, 2~3분 | 최근 10일 |
| profile | 업종·설명·ETF 보수·공매도 잔고 | yfinance | 10분 안팎 | 주 1회 |

## 2차 수집기

```bat
pip install -r requirements-hub.txt      :: pykrx 추가됨
python -m hub run etf --limit 10
python -m hub run options --limit 10
python -m hub run kr_etf --limit 5       :: 한국거래소 접속 시험 겸용
python -m hub run phase2                 :: 전체
```

| 이름 | 내용 | 출처 | 시간(예상) |
|---|---|---|---|
| etf | ETF 구성 종목(운용사 파일: SPDR·Invesco·ProShares·Direxion·ARK), 그 외 상위 10개 + 섹터·자산 비중 | 운용사, yfinance | 5분 안팎 |
| options | 시총 상위 200 + ETF: 30일 ATM 내재변동성, 풋/콜 비율, 왜곡 | yfinance | 10분 안팎 |
| kr_etf | 국내 상장 미국 주식형 ETF: 가격·NAV·괴리율·추적오차·구성 | 한국거래소(pykrx) | 5~10분 |

## 결과 확인
실행이 끝날 때마다 점검표가 나옵니다 (종목 수, 빠진 종목, 최신 날짜, 걸린 시간, 주의 사항).
`[확인 필요]`가 뜨거나 주의 사항이 많으면 그 부분을 그대로 복사해서 알려 주세요.
