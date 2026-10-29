# 홍보 카드 시안 (2026-10-26~28)

`marketing/STRATEGY.md` 연재용 카드 시안을 만들던 스크립트와 결과 이미지. 아직 `hub/cards.py`에 들어가지 않은 실험본.

| 파일 | 내용 | 결과 |
|---|---|---|
| `v2.py` | 공통 틀(밝은 배경·큰 글씨) + "서프라이즈인데 하락"(MSFT)·"고배당의 함정" | 사용자 평: 당연한 얘기 |
| `v2pf.py` | 포트폴리오 위기 테스트 (2008·2022·원화) | 같은 평 |
| `v3.py` | 상황형: "나눠 담았는데 왜 더 빠졌지"(A)·"탭 몇 개 여셨어요"(B, 사이트 캡처) | 내용은 좋아졌으나 광고 같음 |
| `v4.py` | **토스피드 원칙 적용** — '흔한 착각 01' 8장, 제품 언급은 출처·끝 한 줄뿐 | 최신 방향 (`png/v4_*.png`) |

실행: `data/`에 사이트 JSON을 받아 두고(`https://tickermap.kr/api/v1/free/universe.json` → `u.json`, `free/stock/<T>.json` → `<T>.json`, `free/etf/<T>.json` → `etf_<T>.json`, `free/fx.json`), 저장소 루트에서 `python marketing/samples/v4.py`. Playwright·Pretendard(hub/cards_assets) 사용.

배운 점(다음 시안에 그대로): 한 세트 = 한 문장 이야기, 한 장 = 문장 하나 + 숫자 하나, 상황·사람으로 시작, 반대 사례로 균형, '내 거 확인법' 장(저장 유도), 티커맵은 데이터 출처와 마지막 한 줄 '직접 계산해 보기'로만. 조사 문서: claude.ai 문서 "정보형 SNS 콘텐츠·바이럴 조사".
