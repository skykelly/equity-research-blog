/* ============================================
   Global Research Digest — app.js
   ============================================ */

const DATA_URL = "data/articles.json";
const PAGE_SIZE = 18;

const SOURCE_CONFIG = {
  "goldman-sachs": { label: "Goldman Sachs", cls: "gs" },
  "jpmorgan":      { label: "J.P. Morgan",   cls: "jpm" },
  "morgan-stanley":{ label: "Morgan Stanley", cls: "ms" },
};

// ── State ──────────────────────────────────────
let allArticles  = [];
let filtered     = [];
let currentPage  = 1;
let activeSource = "all";
let activeCategory = "all";

// ── DOM refs ───────────────────────────────────
const grid       = document.getElementById("cards-grid");
const loadingEl  = document.getElementById("loading-state");
const emptyEl    = document.getElementById("empty-state");
const loadMoreBtn= document.getElementById("btn-load-more");
const statTotal  = document.getElementById("stat-total");
const statToday  = document.getElementById("stat-today");
const lastUpdEl  = document.getElementById("last-updated");

// ── Bootstrap ──────────────────────────────────
(async function init() {
  try {
    const resp = await fetch(DATA_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    allArticles = await resp.json();

    // Sort: newest first
    allArticles.sort((a, b) => new Date(b.published_date) - new Date(a.published_date));

    updateStats();
    applyFilters();
    setupFilterListeners();
    loadingEl.classList.add("hidden");

  } catch (err) {
    loadingEl.innerHTML = `<p style="color:#ef4444">데이터 로드 실패: ${err.message}</p>
      <p style="font-size:12px;color:#4a5568;margin-top:8px">articles.json이 data/ 폴더에 있는지 확인해주세요.</p>`;
    console.error(err);
  }
})();

// ── Stats ──────────────────────────────────────
function updateStats() {
  statTotal.textContent = allArticles.length.toLocaleString();

  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const recentCount = allArticles.filter(a => new Date(a.published_date) >= sevenDaysAgo).length;
  statToday.textContent = recentCount;

  // Last updated: most recent article date
  if (allArticles.length > 0) {
    const latestDate = allArticles[0].published_date;
    lastUpdEl.textContent = `최근 업데이트: ${formatDate(latestDate)}`;
  }
}

// ── Filter logic ───────────────────────────────
function applyFilters() {
  filtered = allArticles.filter(a => {
    const sourceMatch   = activeSource === "all"   || a.source_id === activeSource;
    const categoryMatch = activeCategory === "all" || a.category  === activeCategory;
    return sourceMatch && categoryMatch;
  });

  currentPage = 1;
  renderCards(true);
}

function setupFilterListeners() {
  document.querySelectorAll(".chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const filterType = btn.dataset.filter;
      const value      = btn.dataset.value;

      // Update active chip in the same group
      document.querySelectorAll(`.chip[data-filter="${filterType}"]`).forEach(c => c.classList.remove("active"));
      btn.classList.add("active");

      if (filterType === "source")   activeSource   = value;
      if (filterType === "category") activeCategory = value;

      applyFilters();
    });
  });

  loadMoreBtn.addEventListener("click", () => {
    currentPage++;
    renderCards(false);
  });
}

// ── Render ─────────────────────────────────────
function renderCards(reset) {
  if (reset) {
    // Remove existing cards (keep loading/empty els)
    grid.querySelectorAll(".article-card").forEach(c => c.remove());
    emptyEl.classList.add("hidden");
  }

  if (filtered.length === 0) {
    emptyEl.classList.remove("hidden");
    loadMoreBtn.classList.add("hidden");
    return;
  }

  const start = (currentPage - 1) * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);

  slice.forEach((article, i) => {
    const card = buildCard(article);
    card.style.animationDelay = `${i * 30}ms`;
    grid.appendChild(card);
  });

  // Show/hide load more
  const shown = Math.min(currentPage * PAGE_SIZE, filtered.length);
  if (shown < filtered.length) {
    loadMoreBtn.textContent = `더 보기 (${filtered.length - shown}개 남음)`;
    loadMoreBtn.classList.remove("hidden");
  } else {
    loadMoreBtn.classList.add("hidden");
  }
}

function buildCard(article) {
  const src = SOURCE_CONFIG[article.source_id] || { label: article.source_name, cls: "" };

  const card = document.createElement("a");
  card.className = "article-card";
  card.href      = article.url;
  card.target    = "_blank";
  card.rel       = "noopener noreferrer";
  card.dataset.source = article.source_id;

  card.innerHTML = `
    <div class="card-source">
      <span class="source-badge ${src.cls}">
        <span class="source-dot ${src.cls}"></span>
        ${escHtml(src.label)}
      </span>
      <span class="card-date">${formatDate(article.published_date)}</span>
    </div>
    <h2 class="card-title">${escHtml(article.title)}</h2>
    <p class="card-summary">${escHtml(article.summary_ko || "요약 준비 중...")}</p>
    <div class="card-footer">
      <span class="category-tag">${escHtml(article.category || "Global Markets")}</span>
      <span class="card-link-icon">↗</span>
    </div>
  `;

  return card;
}

// ── Helpers ────────────────────────────────────
function formatDate(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return dateStr;
  }
}

function escHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
