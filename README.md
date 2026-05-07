# clipnote MVP

작은 로컬 CLI 초안.

## 현재 기능
- URL에서 제목 추출
- `AI` Obsidian vault 자동 탐색 (`~/Library/Application Support/obsidian/obsidian.json`)
- `Papers/YYYY-MM-DD/` 또는 `Links/YYYY-MM-DD/`에 저장
- 같은 URL / 같은 제목 중복 경고
- 볼트 전체 중복 스캔 (`dedupe`)
- 어떤 노트를 남길지 추천 (`dedupe --recommend`)
- 추천 기준으로 keep 노트에 candidate 발췌를 붙이는 merge 보조 (`dedupe --merge-assist`)
- 추천 기준으로 중복 후보를 `Archive/`로 이동하는 반자동 정리 (`dedupe --archive-recommended`)
- merge+archive를 한 번에 도는 `cleanup`
- save 시 HTML에서 summary/key point 초안 생성
- arXiv save 시 API로 저자 / 발행일 / 카테고리 메타데이터 보강
- arXiv 저자가 많을 때는 축약 표시 + 전체 저자 섹션 분리
- 최근 노트를 주간 마크다운으로 묶는 `recap --week`
- `recap --compare-previous`로 직전 같은 기간과 변화 비교
- recap 결과를 Obsidian vault 안 `Recaps/` note로 바로 저장
- recap에 highlights / recurring themes / source breakdown 자동 생성
- recap은 기존 note의 `Brief take` / `Why it matters`도 summary fallback으로 활용
- source별(arXiv/OpenAI/GitHub/Anthropic/Vercel/Hugging Face) summary / why-save 초안 튜닝
- source별 title suffix/prefix 정리로 note 제목과 파일명 정돈
- source/kind/category 기반 tags 자동 생성
- 표준 템플릿 생성

## 사용 예시
```bash
python3 Projects/clipnote/clipnote.py save 'https://arxiv.org/abs/2604.11978' --dry-run
python3 Projects/clipnote/clipnote.py save 'https://arxiv.org/abs/2604.11978'
python3 Projects/clipnote/clipnote.py save 'https://openai.com/index/gpt-5-5-instant/' --kind links
python3 Projects/clipnote/clipnote.py dedupe
python3 Projects/clipnote/clipnote.py dedupe --urls-only
python3 Projects/clipnote/clipnote.py dedupe --recommend
python3 Projects/clipnote/clipnote.py dedupe --urls-only --merge-assist
python3 Projects/clipnote/clipnote.py dedupe --urls-only --merge-assist --apply
python3 Projects/clipnote/clipnote.py dedupe --urls-only --archive-recommended
python3 Projects/clipnote/clipnote.py dedupe --urls-only --archive-recommended --apply
python3 Projects/clipnote/clipnote.py cleanup --urls-only
python3 Projects/clipnote/clipnote.py cleanup --urls-only --apply
python3 Projects/clipnote/clipnote.py save 'https://openai.com/index/gpt-5-5-instant/' --dry-run
python3 Projects/clipnote/clipnote.py recap --week
python3 Projects/clipnote/clipnote.py recap --week --anchor-date 2026-05-07
python3 Projects/clipnote/clipnote.py recap --week --compare-previous
python3 Projects/clipnote/clipnote.py recap --week --output weekly-recap.md
python3 Projects/clipnote/clipnote.py recap --week --save-note
python3 Projects/clipnote/clipnote.py recap --week --save-note --dry-run
```

## 로컬 HTTP 서버 (확장용 MVP)
```bash
cd ~/Projects/clipnote
python3 clipnote_server.py
```

기본 허용 origin:
- `chrome-extension://dojaomlgohpahfibbdbjjnkkpbdoljnf`

확장 manifest에 고정 key를 넣어둬서 unpacked로 로드해도 같은 extension ID를 유지한다.

엔드포인트:
- `GET /health`
- `POST /preview`
- `POST /save`

예:
```bash
curl http://127.0.0.1:8765/health
curl -X POST http://127.0.0.1:8765/preview \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://arxiv.org/abs/2604.11978"}'
```

## Chrome extension MVP

폴더:
- `Projects/clipnote/extension/`

로드 방법:
1. Chrome에서 `chrome://extensions` 열기
2. `Developer mode` 켜기
3. `Load unpacked` 클릭
4. `Projects/clipnote/extension` 폴더 선택
5. 먼저 로컬 서버 실행:

```bash
cd ~/Projects/clipnote
python3 clipnote_server.py
```

예상 extension ID:
- `dojaomlgohpahfibbdbjjnkkpbdoljnf`

현재 기능:
- 현재 탭 URL 자동 읽기
- popup 열면 자동 preview
- title override
- kind override
- save
- save 후 note 자동 열기
- popup에서 `Open` 버튼으로 다시 열기
- save conflict 시 `Open existing`로 기존 note 바로 열기
- duplicate 표시
- 우클릭 메뉴에서 현재 페이지/링크 바로 저장
- 우클릭 전 선택한 텍스트가 있으면 note에 `Selected excerpt`로 함께 저장

context menu:
- 페이지에서 우클릭 → `Preview page in clipnote`
- 페이지에서 우클릭 → `Save page to clipnote`
- 링크에서 우클릭 → `Preview link in clipnote`
- 링크에서 우클릭 → `Save link to clipnote`
- 텍스트를 먼저 드래그 선택한 뒤 저장하면 그 문장이 note에 같이 들어감

Preview 메뉴는 popup을 열어서:
- URL
- 선택 텍스트
- duplicate
- summary draft
를 먼저 확인하게 해준다.

참고:
- extension 파일을 바꿨으면 `chrome://extensions`에서 **Reload** 한 번 해줘야 함
- context menu 저장 결과는 Chrome 알림으로 표시됨
- 저장 성공 시 note를 바로 열도록 시도함

## 다음 후보
- 본문 요약 자동 생성
- source별 관련 인물/회사명 alias 정리
- arXiv 저자 affiliation까지 확장할지 검토
- recap compare에서 source별 키워드 weighting 추가
