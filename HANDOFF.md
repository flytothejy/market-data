# 인수인계 — 티커맵 (2026-10-29)

> 다음 세션이 이 문서부터 읽고 시작. 저장소가 공개라 비밀값·가입자 수치는 적지 않음.
> 사용자: 한국어로 대화. 짧고 쉬운 말, 결정할 것만 묻기. "반영해줘" = design → main 배포.

## 1. 한눈에

- **서비스**: 티커맵(tickermap.kr) — 한국어 미국 주식 정보 사이트. 추천·예측 안 함, 근거·과거 기록만.
- **저장소**: flytothejy/market-data (공개). 기본 브랜치 main, 디자인 작업 브랜치 design.
- **미리보기**: https://design.tickermap.pages.dev/hub/ (design 브랜치, 데이터는 R2 최신 — 빌드 뒤 `preview.yml` 다시 돌려야 새 데이터)
- **관리자**: admin.tickermap.kr (`admin/index.html`, 탭: 개요·사용자·보안 기록·알림·AI 검색·운영·관리자 기록)

## 2. 작업 방식 (꼭 지킬 것)

| 규칙 | 내용 |
|---|---|
| 화면 변경 | design 브랜치 먼저 → 미리보기 확인 → 사용자가 "반영해줘" 하면 main을 design으로 fast-forward 후 push |
| 백엔드·데이터 변경 | main에 바로 (빌드가 돌아야 하므로). 그다음 design에 main 병합 |
| 비밀값 | 저장소·대화에 절대 안 씀. 사용자가 Cloudflare 대시보드·GitHub Secrets에 직접 등록 |
| R2 | 쓰기는 Actions만. 세션의 읽기 전용 토큰: `/root/.config/hub_r2_ro.env` (출력·커밋 금지) |
| 표현 | 추천·예측·'검증'·PRO 표시 금지, 방향(오를지/내릴지) 표시 금지, 과거 통계는 ? 뒤 짧은 문장 |
| 법률 | 법률 전문가 아님을 밝힘. 유사투자자문업 — 유료화 전 법률 검토 필요 |
| 기타 | 사용자 이메일은 식별·SEC User-Agent에만. LM.csv는 공개 저장소에 넣지 않음. 연구용 EODHD 데이터는 사이트에 안 씀 |
| 커밋 | 메시지 끝에 Co-Authored-By/Claude-Session 줄 (시스템이 알려 주는 대로) |
| GitHub API | `gh` GraphQL 안 됨 → `gh api` REST 사용 (예: 워크플로 실행 `gh api -X POST repos/flytothejy/market-data/actions/workflows/<file>/dispatches -f ref=main -f 'inputs[set]=build,check'`) |

## 3. 구조

- **수집·빌드(Python `hub/`)**: `python -m hub run <수집기>` · `hub.yml`이 세트 실행 — `close`(universe·prices·options·build·check), `daily`(전체), `weekly`, 또는 `a,b,c`. Cloudflare Worker(cloudflare/trigger)가 미국 동부 16:20/19:30에 깨움, GitHub cron은 예비.
- **사이트 배포**: `pages.yml` (hub 끝나면 workflow_run으로, main push 때도) → `site/api/v1` 데이터 + `web/` 화면
- **API Worker** `cloudflare/api` (tickermap-api, api.tickermap.kr + workers.dev): Better Auth 로그인·D1·포트폴리오·텔레그램 알림·관리자 API·**AI 문장 검색**. `api.yml`이 main push 때 D1 마이그레이션 + 배포
- **알림**: `hub/alerts.py` (매일, 텔레그램) + 운영 알림(`ops_report`)
- **연구 반영**: `hub/spec/tickermap_spec.json`(값 바꾸지 말 것) — distress·dividend·events·earnmove·지수 근접, research_live 기록

## 4. 최근 한 일 (2026-10-26~29)

1. **홍보 전략** — `marketing/STRATEGY.md`, `headlines.json`(제목 틀·금지 표현). 카드 시안 여러 차례 → 사용자 피드백: 나열형은 공감 없음, 상황형은 광고 같음 → **토스피드 원칙**(본문에 제품 없음, 출처·도구 안내로만)으로 '흔한 착각 01' 시안(`marketing/samples/`, README에 배운 점). 조사 문서는 claude.ai 문서 "정보형 SNS 콘텐츠·바이럴 조사"(사용자 계정).
2. **수집 오류 수정** — alerts KeyError 's'(예상 EPS 0일 때), iShares 비중 열 이름 변경(`Weight (%)` → `Market Weight`, universe·etf 둘 다 대응). 주의 경고(HOLX 상장폐지, XP 실제 폭락, ARK 등 운용사 파일, 시총 불일치)는 **지켜보기로 함**.
3. **AI 문장 검색 (배포 완료)** — 설계 `features/ai-screen/README.md`
   - 검색 화면(`web/screen.html`) 위 '문장으로 찾기' (무지개 테두리·반짝이 아이콘, 예시 3개는 미리 만든 결과)
   - Worker `/ai/screen` (`cloudflare/api/ai.js`, 프롬프트 `ai_prompt.txt`): 문장 → 조건 JSON, 검사, 하루 횟수(로그인 30·비로그인 10, 같은 문장 7일 저장), D1 `ai_log`·`ai_cache` (`migrations/0006_ai.sql`), 기록 1년·계정 삭제 시 삭제
   - 필드 사전 `hub/screen_catalog.py` → build가 `free/screen_catalog.json` 매일 생성 (Worker가 10분 캐시로 읽음)
   - 새 필드 `rev_up_q`·`ni_up_q`(작년 같은 분기보다 늘어난 분기 연속 수, 최대 12)
   - 평가: `features/ai-screen/eval.json` 25문장, Actions **ai-eval** 수동 실행(ALERT_KEY로 제한 건너뜀) → 25/25 (평가에 맞춰 고친 부분 있음)
   - 관리자 'AI 검색' 탭 + 운영 알림에 하루 합계 한 줄
   - 개인정보처리방침에 '문장으로 찾기' 항목·Anthropic 국외 이전 추가
   - 설정: Secret `ANTHROPIC_API_KEY`(등록 완료, 티커맵 전용 키), 선택 변수 `AI_MODEL`(기본 claude-haiku-5-5, temperature 미지원), `AI_LIMIT_USER`, `AI_LIMIT_ANON`, `DATA_URL`

## 5. 진행 중·다음 할 일

| 우선 | 할 일 | 상태·메모 |
|---|---|---|
| 1 | **AI 호출 하루 전체 상한(모든 사용자 합산, 예: 500회) + 분당 상한(예: 5회)** | 사용자에게 제안, 답 대기 중. 상한은 실제 AI 호출만 셈(저장 결과·예시·평가 제외), 걸리면 운영 알림. 나중에 로그인/비로그인 분리 가능 |
| 2 | AI 검색 기록 1~2주 관찰 → 자주 나온 미지원 조건으로 필드 추가, 실패 문장을 eval.json에 추가 | 관리자 'AI 검색' 탭 |
| 3 | 칩 문구: 연속 증가 12는 "12분기 이상"으로 표시 | 작은 개선 |
| 4 | 홍보: v4 방향 사용자 확인 → '흔한 착각 02'(고배당) 등 → `hub/cards.py` 연재 틀로 자동화, 제목 틀 조사(은/는) 처리, 금지 표현 자동 점검, 스레드 API | `marketing/STRATEGY.md` §9 |
| 5 | 사이트 데이터 문제 확인 | TMUS·COP '마지막 배당 삭감' 표시 의심(첫 배당·변동 배당), 시총 상위인데 한국어 이름 없는 종목(RPRX·QSR·RKT·ALNY·MDB·VICI·EIX 등 → `hub/ko_names.csv`), '2006년 이후 삭감 없음'은 데이터 시작 연도라는 점 문구 |
| 6 | 미뤄 둔 것 | 역DCF(spec F5 규칙), 피인수 확정 규칙 실제 사례 확인, 분할 의심 오탐 줄이기(XP 같은 폭락), ARK·GLD·IAU 운용사 주소 |

## 6. 자주 쓰는 확인

```bash
# 최근 실행
gh api 'repos/flytothejy/market-data/actions/runs?per_page=5' --jq '.workflow_runs[] | "\(.name) \(.status) \(.conclusion) \(.created_at)"'
# 수집기 상태(R2 읽기 전용 토큰): hub/_status/<수집기>.json
# 사이트 데이터
curl -s https://tickermap.kr/api/v1/free/universe.json | python3 -c "import json,sys;u=json.load(sys.stdin);print(u['asof'],len(u['rows']))"
# AI 검색 시험 (하루 횟수 씀)
curl -s -X POST https://api.tickermap.kr/ai/screen -H 'origin: https://tickermap.kr' -H 'content-type: application/json' -d '{"q":"배당 4% 넘는 대형주"}'
```

- 로컬 화면 시험: `web/`을 복사하고 `api/v1/free/universe.json`을 옆에 두고 `python3 -m http.server`, Playwright로 확인
- 대기는 foreground sleep 대신 `until …; do sleep N; done`(필요하면 run_in_background)
