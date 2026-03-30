"""
Goldman Sachs Insights Scraper
Target: https://www.goldmansachs.com/insights/
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import hashlib
import re
from typing import Optional

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

BASE_URL = "https://www.goldmansachs.com"
INSIGHTS_URL = "https://www.goldmansachs.com/insights/"

SOURCE_ID = "goldman-sachs"
SOURCE_NAME = "Goldman Sachs"


def make_article_id(url: str) -> str:
    return "gs_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(text: str) -> Optional[str]:
    """Try to parse various date formats into ISO string."""
    if not text:
        return None
    text = text.strip()
    formats = ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try partial match with regex
    match = re.search(r"(\w+ \d+,?\s*\d{4})", text)
    if match:
        for fmt in ["%B %d, %Y", "%B %d %Y", "%b %d, %Y"]:
            try:
                return datetime.strptime(match.group(1).replace(",", ""), "%B %d %Y").strftime("%Y-%m-%d")
            except ValueError:
                continue
    return datetime.today().strftime("%Y-%m-%d")


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    """Scrape Goldman Sachs Insights page for articles."""
    articles = []

    try:
        resp = requests.get(INSIGHTS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[GS] Failed to fetch insights page: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")

    seen_urls = set()
    # GS uses data-gs-uitk-component="card" on <a> tags for article cards
    # Only target /insights/articles/ to avoid podcasts, videos, etc.
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "/insights/articles/" not in href:
            continue

        full_url = href if href.startswith("http") else BASE_URL + href

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        # Extract title from GS card-title component
        title = ""
        title_el = a_tag.select_one('[data-gs-uitk-component="card-title"]')
        if title_el:
            title = title_el.get_text(strip=True)
        else:
            heading = a_tag.find(["h1", "h2", "h3", "h4"])
            if heading:
                title = heading.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Extract date from card-meta component
        date_str = None
        meta_el = a_tag.select_one('[data-gs-uitk-component="card-meta"]')
        if meta_el:
            date_str = parse_date(meta_el.get_text(strip=True))
        if not date_str:
            parent = a_tag.parent
            for _ in range(5):
                if parent is None:
                    break
                date_tag = parent.find(["time", "span", "p"], class_=re.compile(r"date|time|publish", re.I))
                if date_tag:
                    date_str = parse_date(date_tag.get_text())
                    break
                parent = parent.parent

        # Try to extract body snippet from article page (optional, for summarization)
        body = fetch_article_body(full_url)

        articles.append({
            "id": article_id,
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "title": title,
            "url": full_url,
            "published_date": date_str or datetime.today().strftime("%Y-%m-%d"),
            "body": body,
            "summary_ko": "",
            "category": infer_category(title + " " + body[:300]),
            "collected_at": datetime.utcnow().isoformat() + "Z",
        })

        if len(articles) >= max_articles:
            break

    print(f"[GS] Found {len(articles)} new articles")
    return articles


def fetch_article_body(url: str, char_limit: int = 3000) -> str:
    """Fetch and extract main text body from an article page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove nav, footer, script, style
        for tag in soup(["nav", "footer", "script", "style", "header"]):
            tag.decompose()

        # Try article / main content selectors
        for selector in ["article", "main", '[class*="content"]', '[class*="article"]', ".body", "#content"]:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:char_limit]

        # Fallback: all paragraphs
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
        return text[:char_limit]
    except Exception as e:
        print(f"[GS] Failed to fetch body for {url}: {e}")
        return ""


def infer_category(text: str) -> str:
    text_lower = text.lower()
    if any(k in text_lower for k in ["ai", "artificial intelligence", "machine learning", "technology", "tech"]):
        return "AI & Technology"
    if any(k in text_lower for k in ["energy", "climate", "transition", "oil", "renewable"]):
        return "Energy & Climate"
    if any(k in text_lower for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy"]):
        return "Macro & Rates"
    if any(k in text_lower for k in ["equity", "stock", "market", "s&p", "earnings", "valuation"]):
        return "Equity Markets"
    if any(k in text_lower for k in ["credit", "bond", "fixed income", "yield", "debt"]):
        return "Fixed Income"
    if any(k in text_lower for k in ["geopolit", "china", "trade", "tariff", "war", "election"]):
        return "Geopolitics"
    return "Global Markets"
