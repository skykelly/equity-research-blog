"""
J.P. Morgan Insights Scraper
Target: https://www.jpmorgan.com/insights
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
    "Referer": "https://www.jpmorgan.com/",
}

BASE_URL = "https://www.jpmorgan.com"
INSIGHTS_URL = "https://www.jpmorgan.com/insights"

# Also try research subdomain
RESEARCH_URL = "https://www.jpmorgan.com/global/research"

SOURCE_ID = "jpmorgan"
SOURCE_NAME = "J.P. Morgan"


def make_article_id(url: str) -> str:
    return "jpm_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    formats = ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(\w+\s+\d{1,2},?\s*\d{4})", text)
    if match:
        try:
            cleaned = match.group(1).replace(",", "")
            return datetime.strptime(cleaned, "%B %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.today().strftime("%Y-%m-%d")


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    articles = []

    for url_to_scrape in [INSIGHTS_URL, RESEARCH_URL]:
        if len(articles) >= max_articles:
            break
        articles.extend(_scrape_page(url_to_scrape, existing_ids, max_articles - len(articles)))

    print(f"[JPM] Found {len(articles)} new articles")
    return articles


def _scrape_page(page_url: str, existing_ids: set, limit: int) -> list[dict]:
    articles = []

    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[JPM] Failed to fetch {page_url}: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")

    seen_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]

        # JPM insights articles: /insights/category/subcategory/slug (3+ segments)
        # Reject category-level pages like /insights/markets-and-economy/
        path = href.split("?")[0].rstrip("/")
        segments = [s for s in path.split("/") if s]
        if not (("insights" in segments or "research" in segments) and len(segments) >= 4):
            continue

        full_url = href if href.startswith("http") else BASE_URL + href

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        # Extract title
        title = ""
        heading = a.find(["h1", "h2", "h3", "h4", "h5"])
        if heading:
            title = heading.get_text(strip=True)
        else:
            text = re.sub(r"\s+", " ", a.get_text()).strip()
            if len(text) > 20:
                title = text

        # Reject CTA/nav links ("Learn more", "Read more", etc.)
        _CTA = {"learn more", "read more", "view more", "see more", "learn", "read", "view", "explore"}
        if not title or len(title) < 15 or title.lower() in _CTA:
            continue

        # Extract date from surrounding elements
        date_str = None
        parent = a.parent
        for _ in range(6):
            if parent is None:
                break
            for tag in parent.find_all(["time", "span", "div", "p"]):
                tag_text = tag.get_text(strip=True)
                if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}\b", tag_text):
                    date_str = parse_date(tag_text)
                    break
            if date_str:
                break
            parent = parent.parent

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

        for selector in ["article", "main", '[class*="article-body"]', '[class*="content-body"]', ".content", "#main"]:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:char_limit]

        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
        return text[:char_limit]
    except Exception as e:
        print(f"[JPM] Failed to fetch body for {url}: {e}")
        return ""


def infer_category(text: str) -> str:
    text_lower = text.lower()
    if any(k in text_lower for k in ["ai", "artificial intelligence", "machine learning", "technology", "tech", "digital"]):
        return "AI & Technology"
    if any(k in text_lower for k in ["energy", "climate", "transition", "oil", "renewable", "esg"]):
        return "Energy & Climate"
    if any(k in text_lower for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy", "central bank"]):
        return "Macro & Rates"
    if any(k in text_lower for k in ["equity", "stock", "market", "s&p", "earnings", "valuation"]):
        return "Equity Markets"
    if any(k in text_lower for k in ["credit", "bond", "fixed income", "yield", "debt", "spread"]):
        return "Fixed Income"
    if any(k in text_lower for k in ["geopolit", "china", "trade", "tariff", "war", "election", "sanction"]):
        return "Geopolitics"
    if any(k in text_lower for k in ["private equity", "private credit", "alternative", "hedge fund", "real estate"]):
        return "Alternatives"
    return "Global Markets"
