# tickermap-api (Cloudflare Worker + D1)

schema.sql — D1 Console에 붙여넣는 테이블 정의 (Console이 주석·여러 줄 문장을 잘 못 읽어서 한 줄에 한 문장, 주석 없음)

- users: 사용자 (chat_id = 텔레그램 대화방, mode = digest·off)
- devices: 기기코드의 SHA-256 → 사용자 (코드는 브라우저에만)
- tokens: 10분짜리 한 번용 토큰 (kind tg = 텔레그램 연결, dev = 다른 기기 추가)
- watch: 사용자당 후보함 한 줄(JSON 배열). 항목마다 수정 시각 u, 지운 항목은 {t,u,del:1}.
  한 줄로 두는 이유: 무료 요금제는 요청 한 번에 D1 쿼리 50개까지라 항목마다 한 줄이면 큰 후보함 첫 동기화가 막힘

## 포트폴리오

- 로그인한 계정만 저장 (`portfolio` 표, 문서 하나에 포트폴리오 여러 개 — `{ v:2, pfs:[{id, name, items:[{t, w}], start, cap, rb}] }`)
- 개수 한도: 변수 `PF_MAX`(기본 3). 늘릴 때는 이 값과 화면의 `Plan.PF_COUNT`(web/assets/data.js)를 같이 바꿈
- 알림: 관심 종목 + 포트폴리오 종목을 합쳐서 보냄 (포트폴리오 이름 표시)

## 관리자 화면 (admin.tickermap.kr)
- 화면: 저장소 `admin/` → `.github/workflows/admin.yml` → Cloudflare Pages 프로젝트 `tickermap-admin`
- API: `admin.js` — `/admin/me·overview·users·audit·alerts·admin-log` (보기 전용)
- 잠금: ① Cloudflare Access(Zero Trust)로 admin.tickermap.kr 전체 ② 로그인 세션 + 변수 `ADMIN_EMAILS`(쉼표로 여러 개)
- 기록: `admin_audit`(관리자가 본 것, 2년) · `alert_log`(알림 발송 결과, 90일)
- admin.tickermap.kr 가 아닌 주소(*.pages.dev)에서는 예시 숫자만 보임 (쿠키가 닿지 않음)
