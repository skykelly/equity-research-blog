# Global Research Digest — Claude Code 인수인계 문서

## 프로젝트 개요

글로벌 IB/리서치 기관 7곳의 공개 Insights 아티클을
자동 수집하고, GitHub Models(gpt-4o-mini)로 한국어 요약하여 카드형 블로그로 배포하는 시스템.

- **배포**: GitHub Pages (정적 사이트)
- **자동화**: GitHub Actions (매일 KST 10시 cron)
- **요약**: GitHub Models `gpt-4o-mini` (GITHUB_TOKEN 자동 인증, 별도 Secret 불필요)
- **DB**: `data/articles.json` (단일 JSON 파일, 신규 아티클 prepend 방식)

---

## 현재 완료된 작업

### Phase 1 — 프로젝트 구조 ✅
전체 디렉토리 구조 및 파일 생성 완료.

### Phase 2 — 스크래퍼 개발 ✅
7개 소스 스크래퍼 구현 완료. 각 스크래퍼는 동일한 인터페이스를 가짐:
- `fetch_articles(existing_ids: set, max_articles: int) -> list[dict]`
- HTML 파싱 방식 (BeautifulSoup4 + lxml) 또는 RSS (feedparser)
- 중복 방지: URL MD5 해시 기반 ID 생성 후 `existing_ids`와 비교

### Phase 3 — Claude API 요약 파이프라인 ✅
- 150자 이내 한국어 요약 생성
- 이미 `summary_ko`가 있는 아티클은 스킵 (증분 처리)
- API rate limit 방지용 딜레이 내장 (0.5초)

### Phase 4 — 정적 블로그 UI ✅
- `docs/index.html` + `docs/style.css` + `docs/app.js`
- 소스별 필터(GS/JPM/MS) + 카테고리별 필터 (8개 카테고리)
- 카드 클릭 시 원문 링크로 이동 (`target="_blank"`)
- `data/articles.json`을 fetch하여 클라이언트 사이드 렌더링

### Phase 5 — GitHub Actions 자동화 ✅
- `.github/workflows/daily_update.yml`
- 매일 UTC 01:00 (KST 10:00) 실행
- `workflow_dispatch`로 수동 실행 가능 (`initial_run: true` 옵션)
- Job 1: 스크래핑 + 요약 → `articles.json` 커밋
- Job 2: GitHub Pages 배포

### Phase 6 — 시드 데이터 ✅
- `data/articles.json`에 20개 초기 아티클 수동 작성
  - Goldman Sachs: 7개
  - J.P. Morgan: 6개
  - Morgan Stanley: 7개
  - 카테고리: 8종 (AI & Technology, Equity Markets, Macro & Rates, Fixed Income, Energy & Climate, Geopolitics, Alternatives, Global Markets)

---

## 디렉토리 구조

```
equity-research-blog/
├── .github/
│   └── workflows/
│       └── daily_update.yml      # GitHub Actions (스크래핑 + Pages 배포)
├── scraper/
│   ├── gs_scraper.py             # Goldman Sachs Insights 스크래퍼
│   ├── jpm_scraper.py            # J.P. Morgan Insights 스크래퍼
│   ├── ms_scraper.py             # Morgan Stanley Ideas 스크래퍼
│   ├── summarizer.py             # Claude API 한국어 요약 모듈
│   └── run_pipeline.py           # 통합 실행 엔트리포인트
├── data/
│   └── articles.json             # 아티클 DB (자동 업데이트됨)
├── docs/                         # GitHub Pages 서빙 루트
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
├── README.md
└── CLAUDE.md                     # ← 이 파일
```

---

## articles.json 스키마

```json
{
  "id": "gs_<md5_10chars>",         // 소스 접두사 + URL MD5 해시
  "source_id": "goldman-sachs",     // "goldman-sachs" | "jpmorgan" | "morgan-stanley"
  "source_name": "Goldman Sachs",   // 표시 이름
  "title": "원문 영어 제목",
  "url": "https://...",             // 원문 URL (클릭 시 이동)
  "published_date": "2026-03-15",   // ISO 날짜 (YYYY-MM-DD)
  "summary_ko": "한국어 요약 150자", // Claude API 생성
  "category": "AI & Technology",    // 아래 카테고리 목록 참고
  "collected_at": "2026-03-28T01:00:00Z"
}
```

**카테고리 목록** (8개 고정값):
`AI & Technology` / `Equity Markets` / `Macro & Rates` / `Fixed Income` /
`Energy & Climate` / `Geopolitics` / `Alternatives` / `Global Markets`

---

## 로컬 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt

# 초기 수집 (~20개, 처음 한 번만)
ANTHROPIC_API_KEY=sk-ant-xxx python scraper/run_pipeline.py --initial

# 일반 증분 업데이트 (신규 아티클만)
ANTHROPIC_API_KEY=sk-ant-xxx python scraper/run_pipeline.py

# 로컬 블로그 확인 (docs/ 기준)
cd docs && python -m http.server 8080
# → http://localhost:8080
```

> **주의**: `docs/app.js`는 `../data/articles.json` 경로로 fetch함.
> 로컬에서 `docs/` 안에 `data/` 심볼릭 링크를 만들거나, 루트에서 서버를 실행해야 함.

```bash
# 루트에서 실행 시 (권장)
python -m http.server 8080
# → http://localhost:8080/docs/
```

---

## GitHub 배포 설정

### 필요한 Secret
별도 Secret 불필요. `GITHUB_TOKEN`이 Actions에서 자동 발급됨.
(`models: read` 권한은 `daily_update.yml`의 `permissions` 블록에 이미 포함됨)

### GitHub Pages 설정
Settings → Pages → Source: **GitHub Actions** 선택

### 첫 실행 (초기 수집)
Actions 탭 → "Daily Research Update & Deploy" → Run workflow → `initial_run: true`

---

## 현재 알려진 이슈 / 미완성 항목

### 스크래퍼 관련 (우선순위 높음)
1. **실제 스크래핑 미검증**: 각 소스의 현재 HTML 구조에 맞는 셀렉터 검증 필요
   - GS, JPM, MS 모두 SPA(React/Next.js) 기반일 가능성 있음
   - JavaScript 렌더링이 필요한 경우 `playwright` 또는 `selenium` 도입 검토 필요
   - 현재 코드는 정적 HTML 파싱 기준으로 작성됨

2. **날짜 파싱 불안정**: 각 소스의 날짜 포맷이 다양하여 파싱 실패 시 오늘 날짜로 fallback 처리 중. 정확도 개선 필요.

3. **본문 추출 후 body 필드 제거**: `run_pipeline.py`에서 요약 후 `body` 필드를 제거함 (`strip_body()`). 의도된 동작이나, 원문 본문 보존이 필요하면 수정 필요.

### UI 관련
4. **`app.js`의 DATA_URL 경로**: 현재 `../data/articles.json`으로 설정됨. GitHub Pages 배포 시 `daily_update.yml`의 Job 2에서 `docs/data/articles.json`으로 복사하므로 실제 배포에서는 `data/articles.json`으로 변경 필요.

   ```javascript
   // docs/app.js 현재
   const DATA_URL = "../data/articles.json";
   
   // GitHub Pages 배포 후 실제 경로
   const DATA_URL = "data/articles.json";
   ```

5. **모바일 필터 UI**: 카테고리 칩이 많아 모바일에서 줄바꿈이 많이 발생. 드롭다운 또는 스크롤 가능한 수평 스크롤로 개선 여지 있음.

6. **로딩 상태**: 현재 JSON fetch 실패 시 에러 메시지만 표시. 재시도 버튼 추가 권장.

### 자동화 관련
7. **스크래핑 실패 시 silent fail**: 현재 소스 하나가 실패해도 나머지는 계속 진행됨. GitHub Actions Summary에는 기록되나 알림 없음. Slack/이메일 알림 추가 권장.

8. **`--initial` 플래그 동작**: `max_per_source=7`로 설정되어 있어 실제로는 소스당 최대 7개 = 총 21개까지만 수집. 정확히 20개를 원한다면 로직 조정 필요.

---

## 다음 작업 제안 (우선순위 순)

### P0 — 배포 전 필수
- [ ] 각 스크래퍼 실제 동작 확인 (GS/JPM/MS 각 사이트에서 아티클 1개 이상 수집되는지 테스트)
- [ ] `docs/app.js`의 `DATA_URL` 경로 수정 (`data/articles.json`)
- [ ] GitHub 레포 생성 → Secret 등록 → Pages 활성화 → 첫 실행

### P1 — 안정화
- [ ] Playwright 도입 검토 (JS 렌더링 페이지 대응)
- [ ] 스크래핑 실패 시 GitHub Actions Slack/이메일 알림 추가
- [ ] 날짜 파싱 로직 강화 및 테스트

### P2 — 기능 개선
- [ ] 클라이언트 사이드 텍스트 검색 기능 추가
- [ ] RSS 피드 자동 생성 (`articles.json` → `feed.xml`)
- [ ] 모바일 카테고리 필터 UI 개선
- [ ] 신규 아티클 강조 표시 ("NEW" 배지, 최근 24시간 이내)

### P3 — 확장
- [ ] 소스 추가: BofA Global Research (현재 차단됨)
- [ ] 카테고리 자동 분류 정확도 개선 (현재 키워드 기반 → LLM 분류로 교체)
- [ ] 아티클 통계 대시보드 (소스별 발행 빈도, 카테고리 분포 등)

---

## 환경 변수

| 변수 | 용도 | 필수 여부 |
|------|------|----------|
| `GITHUB_TOKEN` | GitHub Models API 요약 (Actions 자동 제공) | 자동 |

---

## 주요 설정값 (run_pipeline.py)

```python
MAX_PER_SOURCE = 10      # 일반 업데이트 시 소스당 최대 수집 수
MAX_TOTAL_ARTICLES = 500 # DB 최대 아티클 수 (초과 시 오래된 것 제거)
# --initial 플래그 시: max_per_source = 7 (소스당 7개 = 총 ~49개)
```

---

## 수집 소스 목록 (7개 활성)

| source_id | source_name | scraper 파일 | 방식 | 비고 |
|---|---|---|---|---|
| goldman-sachs | Goldman Sachs | gs_scraper.py | HTML | /insights/articles/ 필터 |
| jpmorgan | J.P. Morgan | jpm_scraper.py | HTML | path 4단계 이상 필터 |
| morgan-stanley | Morgan Stanley | ms_scraper.py | HTML | aria-label 기반 title |
| blackrock | BlackRock BII | blackrock_scraper.py | HTML | publications 페이지 |
| jefferies | Jefferies | jefferies_scraper.py | HTML | 3개 카테고리 페이지 |
| deloitte | Deloitte Insights | deloitte_scraper.py | HTML | /us/en/insights/ |
| seeking-alpha | Seeking Alpha | seekingalpha_scraper.py | RSS | market-news.xml |

### 차단된 소스 (403/timeout — 재시도 불필요)
| source | 이유 |
|---|---|
| UBS | 403 차단 |
| PIMCO | 403 차단 |
| McKinsey | timeout 차단 |
| Vanguard | 403 차단 (리다이렉트) |
| Fidelity | 403 차단 |

---

## 참고 URL

| 소스 | URL |
|------|-------------|
| Goldman Sachs | https://www.goldmansachs.com/insights/ |
| J.P. Morgan | https://www.jpmorgan.com/insights |
| Morgan Stanley | https://www.morganstanley.com/insights |
| BlackRock BII | https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications |
| Jefferies | https://www.jefferies.com/insights/ |
| Deloitte Insights | https://www.deloitte.com/us/en/insights.html |
| Seeking Alpha | https://seekingalpha.com/market-news.xml (RSS) |
