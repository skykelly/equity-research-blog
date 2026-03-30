# Global Research Digest 📊

**Goldman Sachs · J.P. Morgan · Morgan Stanley** 공개 리서치 아티클을 자동 수집하고 한국어로 요약하는 블로그.

매일 오전 10시 KST에 GitHub Actions가 자동으로 새 아티클을 수집·요약하고 GitHub Pages에 배포합니다.

---

## 프로젝트 구조

```
equity-research-blog/
├── .github/workflows/daily_update.yml   # GitHub Actions (스크래핑 + 배포)
├── scraper/
│   ├── gs_scraper.py                    # Goldman Sachs 스크래퍼
│   ├── jpm_scraper.py                   # J.P. Morgan 스크래퍼
│   ├── ms_scraper.py                    # Morgan Stanley 스크래퍼
│   ├── summarizer.py                    # Claude API 한국어 요약
│   └── run_pipeline.py                  # 통합 실행 스크립트
├── data/
│   └── articles.json                    # 아티클 DB (자동 업데이트)
├── docs/                                # GitHub Pages 루트
│   ├── index.html
│   ├── style.css
│   └── app.js
└── requirements.txt
```

---

## 설정 방법

### 1. GitHub 레포지토리 생성 및 코드 푸시

```bash
git init
git add .
git commit -m "🚀 Initial setup"
git remote add origin https://github.com/YOUR_USERNAME/equity-research-blog.git
git push -u origin main
```

### 2. GitHub Secrets 설정

레포지토리 → Settings → Secrets and variables → Actions → **New repository secret**

| Secret 이름 | 값 |
|------------|-----|
| `ANTHROPIC_API_KEY` | Claude API 키 |

### 3. GitHub Pages 활성화

Settings → Pages → Source: **GitHub Actions**

### 4. 초기 20개 아티클 수집 (첫 실행)

Actions 탭 → "Daily Research Update & Deploy" → **Run workflow** → `initial_run: true`

또는 로컬에서:
```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=your_key python scraper/run_pipeline.py --initial
```

### 5. 자동화 확인

매일 오전 10시 KST에 자동 실행됩니다. 수동 실행은 Actions 탭에서 언제든 가능.

---

## 로컬 개발

```bash
# 의존성 설치
pip install -r requirements.txt

# 스크래핑 테스트 (초기 수집)
ANTHROPIC_API_KEY=your_key python scraper/run_pipeline.py --initial

# 일반 업데이트 테스트
ANTHROPIC_API_KEY=your_key python scraper/run_pipeline.py

# 로컬 서버 (docs/ 폴더 기준)
cd docs && python -m http.server 8080
# → http://localhost:8080
```

---

## 소스

| 기관 | URL | 콘텐츠 |
|------|-----|--------|
| Goldman Sachs | goldmansachs.com/insights | Top of Mind, Outlook |
| J.P. Morgan | jpmorgan.com/insights | Market Outlook, Thematic |
| Morgan Stanley | morganstanley.com/ideas | The EDGE, Research Commentary |

> 본 프로젝트는 각 기관의 **공개 Insights 페이지**만을 대상으로 하며, 투자 권유 목적이 아닙니다.

---

## 기술 스택

- **스크래핑**: Python, BeautifulSoup4, Requests
- **요약**: Claude API (claude-opus-4-5)
- **프론트엔드**: Vanilla HTML/CSS/JS (정적 사이트)
- **자동화**: GitHub Actions (일 1회 cron)
- **배포**: GitHub Pages
