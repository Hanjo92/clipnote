# clipnote Chrome Extension MVP Plan

## Goal

터미널을 열지 않고, Chrome에서 보고 있는 현재 페이지를 바로 `clipnote`로 저장할 수 있게 한다.

핵심은 **새 로직을 확장 안에 많이 넣지 않고**, 이미 만든 Python 엔진(`clipnote.py`)을 계속 활용하는 것이다.

---

## Product shape

### Primary use case

사용자가 Chrome에서 AI 관련 글/논문을 보고 있다가:

1. 확장 아이콘 클릭
2. 현재 탭 URL 자동 인식
3. 제목 / kind / summary draft / duplicate 상태 미리보기
4. Save 클릭
5. 저장 완료 후 note path 확인

즉, UX는 확장이 담당하고,
실제 저장/요약/중복 판정은 Python 엔진이 담당한다.

---

## Recommended architecture

## Option A — local HTTP bridge (recommended)

### Why

MVP 기준 가장 현실적이고 디버깅이 쉽다.

- Chrome extension에서 `fetch('http://127.0.0.1:8765/...')` 호출 가능
- Python 쪽에서 간단한 로컬 서버만 띄우면 됨
- native messaging보다 구현/디버깅 난이도가 낮음
- 이후 Safari/Arc/다른 UI로도 재사용 쉬움

### Components

#### 1) Chrome extension

역할:
- 현재 탭 URL 읽기
- popup UI 제공
- preview 요청
- save 요청
- 결과 렌더링

#### 2) Local bridge server

예: `clipnote_server.py`

역할:
- 확장 요청 수신
- 내부에서 `clipnote.py` 함수 호출
- JSON 응답 반환

#### 3) Existing clipnote engine

역할:
- title cleanup
- summary draft
- arXiv metadata
- duplicate detection
- tags generation
- note save

---

## Data flow

### Preview

1. extension popup opens
2. current tab URL 수집
3. extension → local server `/preview`
4. server → `prepare_note(...)`
5. preview JSON 반환

예상 응답:

```json
{
  "ok": true,
  "url": "https://arxiv.org/abs/2604.11978",
  "title": "The Long-Horizon Task Mirage? Diagnosing Where and Why Agentic Systems Break",
  "kind": "papers",
  "source": "arXiv",
  "path": "Papers/2026-05-07/...md",
  "tags": ["#ai", "#paper", "#arxiv", "#cs-ai"],
  "summary": "...",
  "keyPoints": ["..."],
  "duplicates": {
    "url": ["Papers/2026-04-17/...md"],
    "title": []
  }
}
```

### Save

1. user clicks Save
2. extension → local server `/save`
3. server writes note
4. saved path 반환

예상 응답:

```json
{
  "ok": true,
  "saved": true,
  "path": "Papers/2026-05-07/...md"
}
```

---

## MVP UI

### Popup layout

#### Header
- current tab title
- source badge (`arXiv`, `OpenAI`, `GitHub Changelog` 등)

#### Main fields
- URL (readonly or collapsible)
- Title (editable)
- Kind toggle
  - Auto
  - Paper
  - Link

#### Preview block
- summary draft
- tags
- duplicate warning
- predicted save path

#### Actions
- Preview / Refresh
- Save
- Open folder or copy path (optional, later)

---

## MVP feature scope

### Must-have
- current tab URL 자동 채우기
- preview
- save
- duplicate 경고
- title override
- kind override

### Nice-to-have later
- note saved toast
- open saved note
- recent saves list
- selection text를 Notes 초안으로 포함
- context menu: “Save to AI vault”
- side panel UI

---

## Local server API sketch

### `POST /preview`

Request:

```json
{
  "url": "https://...",
  "kind": "auto",
  "titleOverride": null
}
```

Response:

```json
{
  "ok": true,
  "preview": {
    "title": "...",
    "kind": "links",
    "source": "OpenAI",
    "path": "Links/2026-05-07/...md",
    "tags": ["#ai", "#link", "#openai"],
    "summary": "...",
    "keyPoints": ["..."],
    "duplicateUrls": [],
    "duplicateTitles": []
  }
}
```

### `POST /save`

Request:

```json
{
  "url": "https://...",
  "kind": "auto",
  "titleOverride": null,
  "force": false
}
```

Response:

```json
{
  "ok": true,
  "saved": true,
  "path": "Links/2026-05-07/...md"
}
```

### `GET /health`

Response:

```json
{
  "ok": true,
  "service": "clipnote-server"
}
```

---

## Recommended implementation strategy

### Phase 1 — make clipnote.py reusable as a module

현재 CLI 중심 구조를 조금만 다듬어서,
서버에서 직접 함수 호출하기 쉽게 만든다.

필요한 최소 함수:
- `prepare_note(...)`
- `build_note(...)`
- `load_vault_path(...)`

이미 대부분 있음.

### Phase 2 — add local HTTP server

예: 표준 라이브러리 `http.server` 또는 Flask/FastAPI.

MVP면 표준 라이브러리나 Flask면 충분.

추천 엔드포인트:
- `/health`
- `/preview`
- `/save`

### Phase 3 — build Chrome extension popup

파일 예시:

- `extension/manifest.json`
- `extension/popup.html`
- `extension/popup.js`
- `extension/popup.css`

### Phase 4 — connect and test

시나리오:
- OpenAI 글 저장
- arXiv 논문 저장
- duplicate URL 존재할 때 warning 확인
- title override 저장 확인

---

## Why not native messaging first?

native messaging도 가능하지만, MVP에는 과하다.

단점:
- manifest 등록 필요
- 브라우저별 설정이 번거롭다
- 디버깅이 귀찮다

장점도 있지만,
지금 단계에서는 **로컬 HTTP가 훨씬 빠르게 실사용 MVP를 만들 수 있다.**

---

## Security notes

로컬 서버는:
- `127.0.0.1` only bind
- CORS allowlist를 Chrome extension origin으로 제한
- 외부 네트워크 bind 금지
- write 대상은 기존 clipnote vault 경로로 제한

최소한 이 정도는 넣는 게 좋다.

---

## Suggested first milestone

**Milestone: “one-click save from current tab”**

완료 기준:
- Chrome popup에서 현재 URL 자동 인식
- Preview 가능
- Save 가능
- duplicate warning 표시
- saved path 반환

이게 되면 이미 CLI보다 훨씬 자주 쓰게 될 가능성이 크다.

---

## Practical recommendation

지금은 이 순서가 가장 좋다:

1. `clipnote_server.py` 추가
2. `/preview`, `/save`, `/health` 구현
3. 크롬 popup MVP 구현
4. 실사용
5. 필요하면 context menu / side panel 추가

---

## Short conclusion

가장 현실적인 다음 단계는:

- **Python 엔진 유지**
- **local HTTP bridge 추가**
- **Chrome extension popup으로 감싸기**

즉,
**로직은 지금 코드에 남기고, UX만 브라우저 쪽으로 끌어올리는 구조**가 가장 좋다.
