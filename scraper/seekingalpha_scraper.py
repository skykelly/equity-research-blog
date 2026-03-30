"""
Seeking Alpha Market News RSS Scraper
Target: https://seekingalpha.com/market-news.xml
"""

import hashlib
import re
from datetime import datetime
from typing import Optional

import feedparser

RSS_URL = "https://seekingalpha.com/market-news.xml"

SOURCE_ID = "seeking-alpha"
SOURCE_NAME = "Seeking Alpha"


def make_article_id(url: str) -> str:
    return "sa_" + hashlib.md5(url.encode()).hexdigest()[:10]


def parse_date(entry) -> str:
    # feedparser provides published_parsed as time struct
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:3]).strftime("%Y-%m-%d")
        except Exception:
            pass
    if hasattr(entry, "published") and entry.published:
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"]:
            try:
                return datetime.strptime(entry.published[:25], fmt[:len(entry.published[:25])]).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return datetime.today().strftime("%Y-%m-%d")


def _clean_html(text: str) -> str:
    """Strip HTML tags from RSS summary."""
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_articles(existing_ids: set, max_articles: int = 10) -> list[dict]:
    articles = []
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        print(f"[SeekingAlpha] Failed to parse RSS: {e}")
        return articles

    if not feed.entries:
        print("[SeekingAlpha] No RSS entries found")
        return articles

    for entry in feed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        article_id = make_article_id(url)
        if article_id in existing_ids:
            continue

        title = entry.get("title", "").strip()
        if not title or len(title) < 15:
            continue

        # Body: summary or content field
        body = ""
        if hasattr(entry, "content") and entry.content:
            body = _clean_html(entry.content[0].get("value", ""))
        elif hasattr(entry, "summary"):
            body = _clean_html(entry.summary)
        body = body[:3000]

        published_date = parse_date(entry)

        articles.append({
            "id": article_id,
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "title": title,
            "url": url,
            "published_date": published_date,
            "body": body,
            "summary_ko": "",
            "category": infer_category(title + " " + body[:300]),
            "collected_at": datetime.utcnow().isoformat() + "Z",
        })

        if len(articles) >= max_articles:
            break

    print(f"[SeekingAlpha] Found {len(articles)} new articles")
    return articles


def infer_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["ai", "artificial intelligence", "technology", "tech", "chip", "semiconductor", "nvidia", "microsoft"]):
        return "AI & Technology"
    if any(k in t for k in ["energy", "oil", "gas", "climate", "renewable", "esg", "carbon"]):
        return "Energy & Climate"
    if any(k in t for k in ["rate", "fed", "inflation", "gdp", "recession", "economy", "cpi", "central bank", "treasury"]):
        return "Macro & Rates"
    if any(k in t for k in ["stock", "equity", "s&p", "nasdaq", "earnings", "ipo", "shares", "market"]):
        return "Equity Markets"
    if any(k in t for k in ["bond", "fixed income", "yield", "credit", "debt", "spread", "muni"]):
        return "Fixed Income"
    if any(k in t for k in ["china", "tariff", "trade", "geopolit", "war", "sanction", "election"]):
        return "Geopolitics"
    if any(k in t for k in ["private equity", "hedge fund", "alternative", "real estate", "buyout"]):
        return "Alternatives"
    return "Global Markets"
