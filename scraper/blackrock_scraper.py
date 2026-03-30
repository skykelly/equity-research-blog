"""
BlackRock Investment Institute (BII) Scraper
Target: https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications
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
}

BASE_URL = "https://www.blackrock.com"
PUBLICATIONS_URL = "https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications"

SOURCE_ID = "blackrock"
SOURCE_NAME = "BlackRock BII"

# Category label prefixes embedded in BII anchor text
_CAT_PREFIX = re.compile(
    r"^(Publications|Geopolitics|Market trends?|Demographics?|Outlook|Global\s+insights?|"
    r"Economy|Asset\s+classes?|Themes?|2026\s+INVESTMENT\s+OUTLOOK)\s*",
    re.I,
)


def make_article_id(url: str) -> str:
    return "bii_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.today().strftime("%Y-%m-%d")


def _extract_title_and_date(anchor_text: str):
    """BII anchor text is: [CategoryLabel][Title][Date]|By[Author]"""
    # Strip author suffix
    text = re.sub(r"\|?By.*$", "", anchor_text, flags=re.I).strip()
    # Strip known BII label (e.g. "BlackRock Investment Institute (BII)")
    text = re.sub(r"^BlackRock\s+Investment\s+Institute.*?\)\s*", "", text).strip()
    # Find date
    date_match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}",
        text,
    )
    if date_match:
        date_str = parse_date(date_match.group(0))
        title = text[: date_match.start()].strip()
    else:
        date_str = None
        title = text
    # Strip leading category label
    title = _CAT_PREFIX.sub("", title).strip()
    return title, date_str


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    articles = []
    try:
        resp = requests.get(PUBLICATIONS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[BII] Failed to fetch publications: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "blackrock-investment-institute" not in href:
            continue
        # Require deep article path (>= 6 slashes) — skip category/nav pages
        path = href.split("?")[0]
        if path.count("/") < 6:
            continue
        # Skip index pages
        if path.rstrip("/").endswith(("index.page", "index.html", "/publications", "/outlook")):
            continue

        full_url = href if href.startswith("http") else BASE_URL + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        anchor_text = re.sub(r"\s+", " ", a.get_text()).strip()
        title, date_str = _extract_title_and_date(anchor_text)

        if not title or len(title) < 10:
            continue

        body = _fetch_body(full_url)

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

    print(f"[BII] Found {len(articles)} new articles")
    return articles


def _fetch_body(url: str, char_limit: int = 3000) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()
        for selector in ["article", "main", '[class*="content"]', '[class*="article"]']:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:char_limit]
        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)[:char_limit]
    except Exception:
        return ""


def infer_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["ai", "artificial intelligence", "technology", "tech", "digital", "semiconductor"]):
        return "AI & Technology"
    if any(k in t for k in ["energy", "climate", "transition", "oil", "renewable", "carbon"]):
        return "Energy & Climate"
    if any(k in t for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy", "central bank"]):
        return "Macro & Rates"
    if any(k in t for k in ["equity", "stock", "market", "earnings", "valuation", "s&p"]):
        return "Equity Markets"
    if any(k in t for k in ["credit", "bond", "fixed income", "yield", "debt", "spread"]):
        return "Fixed Income"
    if any(k in t for k in ["geopolit", "china", "trade", "tariff", "war", "sanction"]):
        return "Geopolitics"
    if any(k in t for k in ["private equity", "private credit", "alternative", "real estate", "infrastructure"]):
        return "Alternatives"
    return "Global Markets"
