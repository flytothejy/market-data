# tickermap-api (Cloudflare Worker + D1)

schema.sql — D1 Console에 붙여넣는 테이블 정의 (Console이 주석·여러 줄 문장을 잘 못 읽어서 한 줄에 한 문장, 주석 없음)

- users: 사용자 (chat_id = 텔레그램 대화방, mode = digest·off)
- devices: 기기코드의 SHA-256 → 사용자 (코드는 브라우저에만)
- tokens: 10분짜리 한 번용 토큰 (kind tg = 텔레그램 연결, dev = 다른 기기 추가)
- watch: 사용자당 후보함 한 줄(JSON 배열). 항목마다 수정 시각 u, 지운 항목은 {t,u,del:1}.
  한 줄로 두는 이유: 무료 요금제는 요청 한 번에 D1 쿼리 50개까지라 항목마다 한 줄이면 큰 후보함 첫 동기화가 막힘
