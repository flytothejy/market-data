# 과제 2-6 — 행동주의 13D 표적 예측: 사전 등록 계획

> 작성·고정 2026-10-25 (결과 보기 전). 코드 폴더 `task11`, log 태그 `T11-`. 공통 규약: `../PLAN_phase2.md`.

## 1. 질문
- 가. 반응 확인: 행동주의 펀드의 첫 13D 공시(지분 5% 이상 + 경영 관여 의도)에 주가가 오르나.
- 나. 사전 예측: 앞으로 12개월 안 행동주의 표적이 될 회사를 "시장 대비 부진" 단순 규칙보다 잘 고를 수 있나.

## 2. 행동주의 펀드 목록 (결과 보기 전 고정)
- 업계에서 자주 꼽히는 행동주의 운용사 37곳: Elliott, Starboard, Icahn, Trian, ValueAct, Third Point, Jana, Pershing Square, Corvex, Engaged, Sachem Head, Land & Buildings, Legion, Ancora, Barington, Mantle Ridge, Politan, Cevian, Glenview, Marcato, Blue Harbour, Sarissa, Engine, Impactive, Irenic, Blackwells, Voce, Clinton, Relational, Biglari, Saba, Lion Point, Bulldog, Macellum, Stilwell, FrontFour, Raging.
- SEC CIK 목록(`cik-lookup-data.txt`)에서 이름 규칙으로 찾았다. 저장 위치는 `activist_ciks.json`이다.
  - 펀드와 무관한 같은 이름(예: 'HIGH RIVER GOLD MINES', 개인 'POLITANO JONATHAN')은 뺀다.

## 3. 사건 정의
- 위 CIK가 **제출자**인 원본 13D 공시를 모은다. 서식명은 'SC 13D' 또는 2024-12 이후 'SCHEDULE 13D'이고, 수정분 /A는 뺀다.
- 그 공시 번호(accession)가 우리 표본 회사의 제출 이력에 있으면, 그 회사를 대상으로 한 행동주의 13D다.
- 같은 회사에 365일 안에 여러 건이 있으면 첫 건만 사건으로 본다.

## 4. 표본과 특징
- 과제 1-5 R 패널(수정판). 분기 초 예측일 2011-01 ~ 2024-10, 회사(CIK) 기준 중복은 뺀다.
- 목표: 다음 날 ~ 365일 안 사건이면 1. 사건일부터 365일 안의 예측일은 뺀다.
- **B1 (시장 대비 부진)**: 직전 252거래일 시장 대비 수익률. 낮을수록 표적 가능성이 높다고 본다.
- **M (로지스틱, 설계 칸에서만 맞춤)**: B1 + 아래 특징
  | ID | 정의 |
  |---|---|
  | x_size | log 시가총액 |
  | x_ey | 이익수익률 |
  | x_fcfy | FCF 수익률 |
  | x_cash | 현금/총자산 |
  | x_lev | 장기부채/총자산 |
  | x_ag | 총자산 증가율 |
  | x_ret3 | 직전 3년 시장 대비 수익률 |
  - 절단·결측 처리는 과제 2-2와 같다.

## 5. 평가
- 칸: 종목 배정 × 예측일 연도 홀/짝.
- **검정 3개**
  1. B1 AUC > 0.5
  2. M AUC − B1 AUC > 0
  3. M 상위 10% 적중 − B1 상위 10% 적중 > 0
- p값: 예측일 블록 부트스트랩 2,000회, 단측. 합격 규칙은 같다.

## 6. 반응 확인 (가)
- 13D 공시일 기준, SPY 대비
  - [−1, +1]: 장 마감 뒤 공시가 많다.
  - [−20, −2]: 사전 매집 기간
  - [+2, +250]: 그 뒤 1년
- 13D는 지분 5%를 넘긴 뒤 10일 안에 낸다(2024-02부터 5영업일). 그래서 사전 구간에는 펀드 자신의 매수가 섞인다.

## 7. 한계
- 펀드 목록 밖의 행동주의(작은 펀드, 개인)는 빠진다.
- 13D 없이 5% 미만으로 하는 캠페인은 모른다.

## 변경 이력
