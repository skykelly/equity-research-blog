"""
Jefferies Insights Scraper
Target: https://www.jefferies.com/insights/ (category pages)
"""

import hashlib
import re
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.jefferies.com/",
}

BASE_URL = "https://www.jefferies.com"
CATEGORY_URLS = [
    "https://www.jefferies.com/insights/category/the-big-picture/",
    "https://www.jefferies.com/insights/category/boardroom-intelligence/",
    "https://www.jefferies.com/insights/category/sustainability-and-culture/",
]

SOURCE_ID = "jefferies"
SOURCE_NAME = "Jefferies"


def make_article_id(url: str) -> str:
    return "jef_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}", text)
    if match:
        try:
            return datetime.strptime(match.group(0).replace(",", ""), "%B %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.today().strftime("%Y-%m-%d")


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    articles = []
    seen_urls: set = set()

    for cat_url in CATEGORY_URLS:
        if len(articles) >= max_articles:
            break
        new = _scrape_category(cat_url, existing_ids, seen_urls, max_articles - len(articles))
        articles.extend(new)

    print(f"[Jefferies] Found {len(articles)} new articles")
    return articles


def _scrape_category(page_url: str, existing_ids: set, seen_urls: set, limit: int) -> list[dict]:
    articles = []
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Jefferies] Failed to fetch {page_url}: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Article links: /insights/[category-slug]/[article-slug]
        # Skip category index pages (/insights/category/...)
        if "/insights/" not in href or "/category/" in href:
            continue
        # Extract path only (handles both relative and absolute URLs)
        from urllib.parse import urlparse
        path = urlparse(href).path.rstrip("/")
        path_parts = [s for s in path.split("/") if s]
        # Need: ['insights', category, article-slug] = 3 parts
        if len(path_parts) < 3:
            continue

        full_url = href if href.startswith("http") else BASE_URL + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        # Title: prefer heading inside anchor, then anchor text
        title = ""
        heading = a.find(["h1", "h2", "h3", "h4"])
        if heading:
            title = heading.get_text(strip=True)
        else:
            text = re.sub(r"\s+", " ", a.get_text()).strip()
            if len(text) > 15:
                title = text

        _CTA = {"learn more", "read more", "view more", "explore", "see more"}
        if not title or len(title) < 15 or title.lower() in _CTA:
            continue

        # Date: look in anchor or nearby elements
        date_str = None
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            for tag in parent.find_all(["time", "span", "div", "p"]):
                tag_text = tag.get_text(strip=True)
                if re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}", tag_text):
                    date_str = parse_date(tag_text)
                    break
                if tag.get("datetime"):
                    date_str = parse_date(tag["datetime"])
                    break
            if date_str:
                break
            parent = parent.parent

        body, page_date = _fetch_article_data(full_url)
        # Prefer date found in article page JSON-LD over list-page extraction
        final_date = page_date or date_str or datetime.today().strftime("%Y-%m-%d")

        articles.append({
            "id": article_id,
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "title": title,
            "url": full_url,
            "published_date": final_date,
            "body": body,
            "summary_ko": "",
            "category": infer_category(title + " " + body[:300]),
            "collected_at": datetime.utcnow().isoformat() + "Z",
        })

        if len(articles) >= limit:
            break

    return articles


def _fetch_article_data(url: str, char_limit: int = 3000) -> tuple:
    """Returns (body: str, date: Optional[str])"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract date from JSON-LD
        date = None
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                import json as _json
                d = _json.loads(s.string)
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
        for selector in ["article", "main", '[class*="content"]', '[class*="article"]', ".entry-content", ".post-content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:char_limit], date
        paragraphs = soup.find_all("p")
        body = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)[:char_limit]
        return body, date
    except Exception:
        return "", None


def infer_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["ai", "artificial intelligence", "technology", "tech", "digital", "semiconductor", "data center"]):
        return "AI & Technology"
    if any(k in t for k in ["energy", "climate", "transition", "oil", "renewable", "carbon", "sustainability"]):
        return "Energy & Climate"
    if any(k in t for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy", "central bank"]):
        return "Macro & Rates"
    if any(k in t for k in ["equity", "stock", "market", "earnings", "valuation", "ipo", "s&p"]):
        return "Equity Markets"
    if any(k in t for k in ["credit", "bond", "fixed income", "yield", "debt", "spread"]):
        return "Fixed Income"
    if any(k in t for k in ["geopolit", "china", "trade", "tariff", "war", "sanction", "india", "japan"]):
        return "Geopolitics"
    if any(k in t for k in ["private equity", "secondary market", "alternative", "real estate", "infrastructure"]):
        return "Alternatives"
    return "Global Markets"
