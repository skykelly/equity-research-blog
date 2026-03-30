"""
Config-Driven Universal Scraper
Reads per-source config from sources.json and handles all scraping logic.

Title strategies:
  gs_card               — GS data-gs-uitk-component="card-title" selector
  aria_label_then_heading — aria-label first, then heading (Morgan Stanley)
  heading               — first heading element inside anchor
  bii_anchor_text       — BlackRock BII anchor-text parsing

Date strategies:
  gs_card               — GS data-gs-uitk-component="card-meta" selector
  surrounding_elements  — search parent elements for month-name date text
  article_jsonld        — fetch article page and extract JSON-LD datePublished
  bii_anchor_text       — BlackRock BII anchor-text date extraction
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

_CTA = {
    "learn more", "read more", "view more", "explore", "see more",
    "learn", "read", "view",
}

_BII_CAT_PREFIX = re.compile(
    r"^(Publications|Geopolitics|Market trends?|Demographics?|Outlook|"
    r"Global\s+insights?|Economy|Asset\s+classes?|Themes?|"
    r"2026\s+INVESTMENT\s+OUTLOOK)\s*",
    re.I,
)

_CATEGORY_KEYWORDS = {
    "AI & Technology": [
        "ai", "artificial intelligence", "machine learning", "technology",
        "tech", "digital", "semiconductor", "data center",
    ],
    "Energy & Climate": [
        "energy", "climate", "transition", "oil", "renewable",
        "carbon", "sustainability", "esg",
    ],
    "Macro & Rates": [
        "rate", "fed", "inflation", "macro", "gdp", "recession",
        "economy", "central bank", "monetary",
    ],
    "Equity Markets": [
        "equity", "stock", "market", "earnings", "valuation", "ipo", "s&p",
    ],
    "Fixed Income": [
        "credit", "bond", "fixed income", "yield", "debt", "spread", "muni",
    ],
    "Geopolitics": [
        "geopolit", "china", "trade", "tariff", "war", "sanction",
        "india", "japan", "election",
    ],
    "Alternatives": [
        "private equity", "private credit", "secondary market", "alternative",
        "real estate", "infrastructure", "hedge fund",
    ],
}


class UniversalScraper:
    def __init__(self, source_config: dict):
        self.config = source_config
        self.headers = source_config.get("headers", {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })

    def fetch(self, existing_ids: set, max_articles: int) -> list[dict]:
        if self.config.get("type") == "rss":
            return self._fetch_rss(existing_ids, max_articles)
        return self._fetch_html(existing_ids, max_articles)

    # ── HTML scraping ───────────────────────────────────────────────

    def _fetch_html(self, existing_ids: set, max_articles: int) -> list[dict]:
        articles: list[dict] = []
        seen_urls: set = set()

        for index_url in self.config["index_urls"]:
            if len(articles) >= max_articles:
                break
            remaining = max_articles - len(articles)
            new = self._scrape_index(index_url, existing_ids, seen_urls, remaining)
            articles.extend(new)

        name = self.config["source_name"]
        print(f"[{name}] Found {len(articles)} new articles")
        return articles

    def _scrape_index(
        self, page_url: str, existing_ids: set, seen_urls: set, limit: int
    ) -> list[dict]:
        articles: list[dict] = []
        name = self.config["source_name"]

        try:
            resp = requests.get(page_url, headers=self.headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[{name}] Failed to fetch {page_url}: {e}")
            return articles

        soup = BeautifulSoup(resp.text, "lxml")

        for a in soup.find_all("a", href=True):
            if len(articles) >= limit:
                break

            href = a["href"]
            if not self._link_passes_filter(href):
                continue

            base = self.config.get("base_url", "")
            full_url = href if href.startswith("http") else base + href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            article_id = self._make_id(full_url)
            if article_id in existing_ids:
                continue

            title = self._extract_title(a)
            if not title:
                continue
            if len(title) < self.config.get("min_title_length", 10):
                continue
            if self.config.get("cta_filter") and title.lower() in _CTA:
                continue

            body, date = self._extract_body_and_date(a, full_url)

            articles.append({
                "id": article_id,
                "source_id": self.config["source_id"],
                "source_name": self.config["source_name"],
                "title": title,
                "url": full_url,
                "published_date": date or datetime.today().strftime("%Y-%m-%d"),
                "body": body,
                "summary_ko": "",
                "category": self._infer_category(title + " " + body[:300]),
                "collected_at": datetime.utcnow().isoformat() + "Z",
            })

        return articles

    # ── RSS scraping ────────────────────────────────────────────────

    def _fetch_rss(self, existing_ids: set, max_articles: int) -> list[dict]:
        try:
            import feedparser
        except ImportError:
            print(f"[{self.config['source_name']}] feedparser not installed")
            return []

        name = self.config["source_name"]
        articles: list[dict] = []

        for feed_url in self.config.get("index_urls", []):
            if len(articles) >= max_articles:
                break
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    if len(articles) >= max_articles:
                        break
                    url = entry.get("link", "")
                    if not url:
                        continue
                    article_id = self._make_id(url)
                    if article_id in existing_ids:
                        continue
                    title = entry.get("title", "").strip()
                    if not title or len(title) < 10:
                        continue

                    date = None
                    if entry.get("published_parsed"):
                        try:
                            date = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                        except Exception:
                            pass
                    if not date:
                        date = self._parse_date(entry.get("published", ""))

                    raw_body = (
                        entry.get("summary", "")
                        or (entry.get("content") or [{}])[0].get("value", "")
                    )
                    body = re.sub(r"<[^>]+>", " ", raw_body)[:3000]

                    articles.append({
                        "id": article_id,
                        "source_id": self.config["source_id"],
                        "source_name": self.config["source_name"],
                        "title": title,
                        "url": url,
                        "published_date": date or datetime.today().strftime("%Y-%m-%d"),
                        "body": body,
                        "summary_ko": "",
                        "category": self._infer_category(title + " " + body[:300]),
                        "collected_at": datetime.utcnow().isoformat() + "Z",
                    })
            except Exception as e:
                print(f"[{name}] RSS error for {feed_url}: {e}")

        print(f"[{name}] Found {len(articles)} new articles")
        return articles

    # ── Link filter ─────────────────────────────────────────────────

    def _link_passes_filter(self, href: str) -> bool:
        lf = self.config.get("link_filter", {})

        if "must_contain" in lf and lf["must_contain"] not in href:
            return False
        if "must_not_contain" in lf and lf["must_not_contain"] in href:
            return False

        path = href.split("?")[0]

        if "min_path_depth" in lf and path.count("/") < lf["min_path_depth"]:
            return False

        if "skip_suffixes" in lf:
            stripped = path.rstrip("/")
            if any(stripped.endswith(s) for s in lf["skip_suffixes"]):
                return False

        if "min_path_segments" in lf or "path_contains_any" in lf:
            parsed_path = urlparse(href).path.rstrip("/")
            parts = [s for s in parsed_path.split("/") if s]
            if "min_path_segments" in lf and len(parts) < lf["min_path_segments"]:
                return False
            if "path_contains_any" in lf and not any(
                kw in parts for kw in lf["path_contains_any"]
            ):
                return False

        return True

    # ── Title extraction ────────────────────────────────────────────

    def _extract_title(self, anchor) -> str:
        strategy = self.config.get("title_strategy", "heading")

        if strategy == "gs_card":
            el = anchor.select_one('[data-gs-uitk-component="card-title"]')
            if el:
                return el.get_text(strip=True)
            h = anchor.find(["h1", "h2", "h3", "h4"])
            return h.get_text(strip=True) if h else ""

        if strategy == "aria_label_then_heading":
            title = anchor.get("aria-label", "").strip()
            if title:
                return title
            h = anchor.find(["h2", "h3", "h1", "h4"])
            if h:
                return h.get_text(strip=True)
            text = anchor.get_text(strip=True)
            return text if len(text) > 20 else ""

        if strategy == "heading":
            h = anchor.find(["h1", "h2", "h3", "h4", "h5"])
            if h:
                return h.get_text(strip=True)
            text = re.sub(r"\s+", " ", anchor.get_text()).strip()
            return text if len(text) > 20 else ""

        if strategy == "bii_anchor_text":
            text = re.sub(r"\s+", " ", anchor.get_text()).strip()
            title, _ = self._bii_parse_anchor(text)
            return title

        return ""

    # ── Body + date extraction ──────────────────────────────────────

    def _extract_body_and_date(self, anchor, url: str):
        strategy = self.config.get("date_strategy", "surrounding_elements")

        if strategy == "gs_card":
            date = None
            meta = anchor.select_one('[data-gs-uitk-component="card-meta"]')
            if meta:
                date = self._parse_date(meta.get_text(strip=True))
            if not date:
                date = self._date_from_surroundings(anchor)
            return self._fetch_body(url), date

        if strategy == "article_jsonld":
            body, date = self._fetch_article_data(url)
            if not date:
                date = self._date_from_surroundings(anchor)
            return body, date

        if strategy == "bii_anchor_text":
            text = re.sub(r"\s+", " ", anchor.get_text()).strip()
            _, date = self._bii_parse_anchor(text)
            return self._fetch_body(url), date

        # Default: surrounding_elements
        return self._fetch_body(url), self._date_from_surroundings(anchor)

    def _date_from_surroundings(self, anchor) -> Optional[str]:
        parent = anchor.parent
        for _ in range(6):
            if parent is None:
                break
            for tag in parent.find_all(["time", "span", "div", "p"]):
                tag_text = tag.get_text(strip=True)
                if re.search(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}",
                    tag_text,
                ):
                    return self._parse_date(tag_text)
                if tag.get("datetime"):
                    return self._parse_date(tag["datetime"])
            parent = parent.parent
        return None

    # ── Page fetching ───────────────────────────────────────────────

    def _fetch_body(self, url: str, char_limit: int = 3000) -> str:
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
                tag.decompose()
            for selector in [
                "article", "main", '[class*="content"]', '[class*="article"]',
                ".entry-content", ".post-content",
            ]:
                el = soup.select_one(selector)
                if el:
                    text = el.get_text(separator=" ", strip=True)
                    if len(text) > 200:
                        return text[:char_limit]
            paragraphs = soup.find_all("p")
            return " ".join(
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 50
            )[:char_limit]
        except Exception:
            return ""

    def _fetch_article_data(self, url: str, char_limit: int = 3000):
        """Returns (body, date) by fetching article page and extracting JSON-LD datePublished."""
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            date = None
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    d = json.loads(s.string)
                    for item in d.get("@graph", [d]):
                        val = item.get("datePublished") or item.get("dateCreated")
                        if val and re.match(r"\d{4}-\d{2}-\d{2}", val):
                            date = val[:10]
                            break
                    if date:
                        break
                except Exception:
                    pass

            for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
                tag.decompose()
            for selector in [
                "article", "main", '[class*="content"]', '[class*="article"]',
                ".entry-content", ".post-content",
            ]:
                el = soup.select_one(selector)
                if el:
                    text = el.get_text(separator=" ", strip=True)
                    if len(text) > 200:
                        return text[:char_limit], date
            paragraphs = soup.find_all("p")
            body = " ".join(
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 50
            )[:char_limit]
            return body, date
        except Exception:
            return "", None

    # ── Source-specific helpers ─────────────────────────────────────

    def _bii_parse_anchor(self, anchor_text: str):
        """BlackRock BII: extract (title, date) from raw anchor text."""
        text = re.sub(r"\|?By.*$", "", anchor_text, flags=re.I).strip()
        text = re.sub(r"^BlackRock\s+Investment\s+Institute.*?\)\s*", "", text).strip()
        date_match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}",
            text,
        )
        if date_match:
            date_str = self._parse_date(date_match.group(0))
            title = text[: date_match.start()].strip()
        else:
            date_str = None
            title = text
        title = _BII_CAT_PREFIX.sub("", title).strip()
        return title, date_str

    # ── Utilities ───────────────────────────────────────────────────

    def _make_id(self, url: str) -> str:
        prefix = self.config.get("id_prefix", self.config["source_id"][:3])
        return f"{prefix}_{hashlib.md5(url.encode()).hexdigest()[:10]}"

    def _parse_date(self, text: str) -> Optional[str]:
        if not text:
            return None
        text = text.strip()
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}",
            text,
        )
        if match:
            try:
                return datetime.strptime(
                    match.group(0).replace(",", ""), "%B %d %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _infer_category(self, text: str) -> str:
        t = text.lower()
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if any(k in t for k in keywords):
                return category
        return "Global Markets"
