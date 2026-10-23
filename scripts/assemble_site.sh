#!/usr/bin/env bash
# 사이트 조립 (pages.yml 본 배포·preview.yml 미리보기 공통) — data/hub/site 는 미리 R2에서 받아 둠
set -e
rm -rf _site && mkdir -p _site/hub
cp -r docs/. _site/
cp -r web/. _site/hub/ 2>/dev/null || true
if [ -d data/hub/site/api ]; then cp -r data/hub/site/api _site/api; fi
if [ -d data/hub/site/cards ]; then cp -r data/hub/site/cards _site/cards; fi   # 주간 홍보 카드
# 예전 컨센서스 페이지: 허브 데이터로 만든 것을 우선 사용
if [ -f _site/api/v1/free/consensus_page.json ]; then cp _site/api/v1/free/consensus_page.json _site/consensus_data.json; fi
python -m hub.static_pages _site     # 검색엔진용 종목·투자자 정적 페이지, 사이트맵
# 화면 파일이 바뀌면 브라우저가 예전 것을 쓰지 않게 주소에 버전 붙이기 (assets/ui.js → assets/ui.js?v=커밋)
V=${GITHUB_SHA::8}
find _site/hub -name '*.html' -print0 | xargs -0 sed -i -E "s#(assets/[A-Za-z0-9_.-]+\.(js|css))\"#\1?v=$V\"#g"
# 앱처럼 설치(PWA): 모든 화면에 manifest·테마 색·아이콘, 서비스 워커 버전
find _site/hub -name '*.html' -print0 | xargs -0 sed -i 's#<link rel="icon" href="assets/icon.svg" type="image/svg+xml">#&\n<link rel="manifest" href="manifest.webmanifest">\n<meta name="theme-color" content="\#fafaf8">\n<link rel="apple-touch-icon" href="assets/app/apple-180.png">\n<meta name="apple-mobile-web-app-title" content="티커맵">#'
sed -i "s/__V__/$V/" _site/hub/sw.js
touch _site/.nojekyll
printf '/  /hub/  301\n' > _site/_redirects            # Cloudflare Pages 전용 (GitHub Pages는 무시)
# 네이버 소유 확인 파일: Cloudflare가 .html 주소를 .html 없는 주소로 308 보내서 확인이 실패하지 않게, 같은 주소로 그대로 내용 응답
printf '/naver69d79dc06402cfbd09ebfe0ce6673965.html  /naver-site-verification.txt  200\n' >> _site/_redirects
cp _site/naver-site-verification.txt _site/naver69d79dc06402cfbd09ebfe0ce6673965.html   # GitHub Pages용
du -sh _site; find _site -type f | wc -l
