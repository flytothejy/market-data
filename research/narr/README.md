# 내러티브 국면 엔진 (2026-11 목업 세션)

레벨1 이야기 → 레벨2 층(역할 틀) → 레벨3 종목. 국면은 층까지만, 2분기 연속 시 확정.
규칙 상세는 스킬 `tickermap-data-lab` §3 참고.

## 실행 위치
스크립트는 상대 경로(`narr/...`, `r2dl/...`, `secdl/...`)를 씀 → **`research/` 폴더에서** 실행.

```bash
cd research
# 1) SEC 분기 패널 (secdl/{TICKER}.json = data.sec.gov companyfacts, UA "TickerMap research tickermap.kr")
python narr/panel_long.py        # → narr/panel_long.csv (커밋돼 있음, 2026-11-06 기준)
# 2) 국면 판정
python -c "import sys; sys.path.insert(0,'narr'); import roles; spec,C,PD,LF = roles.narrative3('narr/narratives/memory.yaml','2015Q1','2026Q3'); print(roles.verdict(spec,C))"
# 3) 목업용 JSON (r2dl/px_YYYY.parquet, r2dl/tenk_newsents.parquet 필요 — R2에서 받기)
python narr/export2.py; python narr/export_rich.py
```
`r2dl/`, `secdl/`, `narrmock/`는 커밋하지 않음(.gitignore). R2 열쇠는 절대 커밋 금지.

## 파일
- `roles.py` 핵심 엔진(역할 단계·층 집계·확정·판정) / `narratives/*.yaml` 이야기 설계
- `panel_long.py` SEC → 분기 패널 / `export*.py` 목업 데이터 / `stage.py`·`build.py`·`chart.py` 초기 버전
- 목업 화면: Design 아티팩트 "티커맵 시장 내러티브 탭 목업"
