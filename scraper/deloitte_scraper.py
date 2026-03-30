"""
Deloitte Insights Scraper
Target: https://www.deloitte.com/us/en/insights.html
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
    "Referer": "https://www.deloitte.com/",
}

BASE_URL = "https://www.deloitte.com"
INSIGHTS_URL = "https://www.deloitte.com/us/en/insights.html"

SOURCE_ID = "deloitte"
SOURCE_NAME = "Deloitte Insights"

# Skip pure navigation/hub pages and research-center index pages
_NAV_SLUGS = {
    "about-deloitte-insights", "deloitte-insights-magazine", "top-10-business-insights",
    "governance-and-board", "environmental-social-governance",
}
_SKIP_PATH_SEGMENTS = {"research-centers"}  # skip entire /research-centers/ tree


def make_article_id(url: str) -> str:
    return "del_" + hashlib.md5(url.encode()).hexdigest()[:10]


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
    try:
        resp = requests.get(INSIGHTS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Deloitte] Failed to fetch insights page: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "lxml")
    seen_urls: set = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]  # Strip query params

        # Must be a Deloitte insights article path
        if "/us/en/insights/" not in href:
            continue
        if not href.endswith(".html"):
            continue

        # Skip known nav/hub pages and research-center trees
        slug = href.rstrip("/").split("/")[-1].replace(".html", "")
        if slug in _NAV_SLUGS or slug in ("insights", ""):
            continue
        parts = [p for p in href.split("/") if p]
        if any(seg in _SKIP_PATH_SEGMENTS for seg in parts):
            continue

        # Require at least 2 path segments under /insights/
        try:
            ins_idx = parts.index("insights")
        except ValueError:
            continue
        if len(parts) - ins_idx < 3:
            continue

        full_url = href if href.startswith("http") else BASE_URL + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        article_id = make_article_id(full_url)
        if article_id in existing_ids:
            continue

        # Title: prefer heading inside anchor, else anchor text
        title = ""
        heading = a.find(["h2", "h3", "h4", "h1"])
        if heading:
            title = heading.get_text(strip=True)
        else:
            text = re.sub(r"\s+", " ", a.get_text()).strip()
            if len(text) > 15:
                title = text

        _CTA = {"learn more", "read more", "view more", "explore", "read the report"}
        if not title or len(title) < 15 or title.lower() in _CTA:
            continue

        # Date: look in parent elements
        date_str = None
        parent = a.parent
        for _ in range(6):
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

        if len(articles) >= max_articles:
            break

    print(f"[Deloitte] Found {len(articles)} new articles")
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
        for selector in ["article", "main", '[class*="content"]', '[class*="article"]', ".rich-text"]:
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
    if any(k in t for k in ["ai", "artificial intelligence", "technology", "tech", "digital", "cloud", "cyber", "deepfake"]):
        return "AI & Technology"
    if any(k in t for k in ["energy", "climate", "transition", "oil", "renewable", "carbon", "esg", "sustainability"]):
        return "Energy & Climate"
    if any(k in t for k in ["rate", "fed", "inflation", "macro", "gdp", "recession", "economy", "central bank", "consumer"]):
        return "Macro & Rates"
    if any(k in t for k in ["equity", "stock", "market", "earnings", "valuation", "ipo"]):
        return "Equity Markets"
    if any(k in t for k in ["credit", "bond", "fixed income", "yield", "debt", "spread"]):
        return "Fixed Income"
    if any(k in t for k in ["geopolit", "china", "trade", "tariff", "war", "sanction", "regulation"]):
        return "Geopolitics"
    if any(k in t for k in ["private equity", "alternative", "real estate", "infrastructure", "m&a"]):
        return "Alternatives"
    return "Global Markets"
