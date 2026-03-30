"""
Morgan Stanley Ideas Scraper
Target: https://www.morganstanley.com/ideas
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
    "Referer": "https://www.morganstanley.com/",
}

BASE_URL = "https://www.morganstanley.com"
IDEAS_URL = "https://www.morganstanley.com/insights"

# Category-specific pages on MS Insights (verified valid paths)
CATEGORY_URLS = [
    "https://www.morganstanley.com/insights/topics/artificial-intelligence",
    "https://www.morganstanley.com/insights/topics/interest-rates",
    "https://www.morganstanley.com/insights/topics/investing",
]

SOURCE_ID = "morgan-stanley"
SOURCE_NAME = "Morgan Stanley"


def make_article_id(url: str) -> str:
    return "ms_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    formats = ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%B %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(\w+\s+\d{1,2},?\s*\d{4}|\w+\s+\d{4})", text)
    if match:
        for fmt in ["%B %d %Y", "%b %d %Y", "%B %Y"]:
            try:
                cleaned = match.group(1).replace(",", "")
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return datetime.today().strftime("%Y-%m-%d")


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    articles = []
    scraped_urls = set()

    # Scrape main ideas page + category pages
    for page_url in [IDEAS_URL] + CATEGORY_URLS:
        if len(articles) >= max_articles:
            break
        new = _scrape_page(page_url, existing_ids, scraped_urls, max_articles - len(articles))
        articles.extend(new)

    print(f"[MS] Found {len(articles)} new articles")
    return articles


def _scrape_page(page_url: str, existing_ids: set, scraped_urls: set, limit: int) -> list[dict]:
    articles = []

    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[MS] Failed to fetch {page_url}: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]

        # MS insights articles live at /insights/articles/[slug]
        if "/insights/articles/" not in href:
            continue

        full_url = href if href.startswith("http") else BASE_URL + href

        if full_url in scraped_urls:
            continue
        scraped_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        # MS: title is in aria-label, or heading, or anchor text
        title = a.get("aria-label", "").strip()
        if not title:
            heading = a.find(["h2", "h3", "h1", "h4"])
            if heading:
                title = heading.get_text(strip=True)
        if not title:
            text = a.get_text(strip=True)
            if len(text) > 20:
                title = text

        if not title or len(title) < 10:
            continue

        # Extract date
        date_str = None
        parent = a.parent
        for _ in range(6):
            if parent is None:
                break
            for tag in parent.find_all(["time", "span", "div", "p"]):
                tag_text = tag.get_text(strip=True)
                if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{0,2},?\s*\d{4}\b", tag_text):
                    date_str = parse_date(tag_text)
                    break
                if tag.get("datetime"):
                    date_str = parse_date(tag["datetime"])
                    break
            if date_str:
                break
            parent = parent.parent

        body = fetch_article_body(full_url)

        # Infer category from URL path too
        category_hint = href.split("/insights/articles/")[-1].split("/")[0] if "/insights/articles/" in href else ""

        articles.append({
            "id": article_id,
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "title": title,
            "url": full_url,
            "published_date": date_str or datetime.today().strftime("%Y-%m-%d"),
            "body": body,
            "summary_ko": "",
            "category": infer_category(title + " " + body[:300] + " " + category_hint),
            "collected_at": datetime.utcnow().isoformat() + "Z",
        })

        if len(articles) >= limit:
            break

    return articles


def fetch_article_body(url: str, char_limit: int = 3000) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()

        for selector in ["article", "main", '[class*="article"]', '[class*="ideas-content"]', ".content", "#content"]:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:char_limit]

        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
        return text[:char_limit]
    except Exception as e:
        print(f"[MS] Failed to fetch body for {url}: {e}")
        return ""


def infer_category(text: str) -> str:
    text_lower = text.lower()
    if any(k in text_lower for k in ["ai", "artificial intelligence", "machine learning", "technology", "tech", "semiconductor", "digital"]):
        return "AI & Technology"
    if any(k in text_lower for k in ["energy", "climate", "transition", "oil", "renewable", "esg", "carbon"]):
        return "Energy & Climate"
    if any(k in text_lower for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy", "central bank", "monetary"]):
        return "Macro & Rates"
    if any(k in text_lower for k in ["equity", "stock", "market", "s&p", "earnings", "valuation", "outlook"]):
        return "Equity Markets"
    if any(k in text_lower for k in ["credit", "bond", "fixed income", "yield", "debt", "spread", "muni"]):
        return "Fixed Income"
    if any(k in text_lower for k in ["geopolit", "china", "trade", "tariff", "war", "election", "sanction", "geostrateg"]):
        return "Geopolitics"
    if any(k in text_lower for k in ["private equity", "private credit", "alternative", "real asset", "real estate", "infrastructure"]):
        return "Alternatives"
    if any(k in text_lower for k in ["market-outlook", "investment-strateg"]):
        return "Equity Markets"
    return "Global Markets"
