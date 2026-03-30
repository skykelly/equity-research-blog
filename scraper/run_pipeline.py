"""
Main pipeline: scrape → summarize → update articles.json
Run: python scraper/run_pipeline.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from gs_scraper import fetch_articles as fetch_gs
from jpm_scraper import fetch_articles as fetch_jpm
from ms_scraper import fetch_articles as fetch_ms
from blackrock_scraper import fetch_articles as fetch_bii
from jefferies_scraper import fetch_articles as fetch_jef
from summarizer import summarize_articles

DATA_FILE = Path(__file__).parent.parent / "data" / "articles.json"
MAX_PER_SOURCE = 10  # Max new articles to collect per source per run
MAX_TOTAL_ARTICLES = 500  # Cap DB size to avoid unbounded growth


def load_existing_articles() -> list[dict]:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles(articles: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"[Pipeline] Saved {len(articles)} articles to {DATA_FILE}")


def run_pipeline(initial_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"[Pipeline] Starting at {datetime.utcnow().isoformat()}Z")
    print(f"[Pipeline] Mode: {'Initial (20 articles)' if initial_run else 'Daily update'}")
    print(f"{'='*60}\n")

    # Load existing articles
    existing = load_existing_articles()
    existing_ids = {a["id"] for a in existing}
    print(f"[Pipeline] Existing articles: {len(existing)}")

    max_per_source = 7 if initial_run else MAX_PER_SOURCE

    # Scrape each source
    new_articles = []

    sources = [
        ("Goldman Sachs",    fetch_gs),
        ("J.P. Morgan",      fetch_jpm),
        ("Morgan Stanley",   fetch_ms),
        ("BlackRock BII",    fetch_bii),
        ("Jefferies",        fetch_jef),
    ]

    for name, fetcher in sources:
        print(f"\n[Pipeline] Scraping {name}...")
        try:
            articles = fetcher(existing_ids=existing_ids, max_articles=max_per_source)
            new_articles.extend(articles)
        except Exception as e:
            print(f"[Pipeline] ERROR scraping {name}: {e}")

    print(f"\n[Pipeline] Total new articles found: {len(new_articles)}")

    if not new_articles:
        print("[Pipeline] No new articles found. DB is up to date.")
        return

    # Remove body text before saving (not needed in final DB, saves space)
    def strip_body(articles):
        for a in articles:
            a.pop("body", None)
        return articles

    # Summarize new articles
    print("\n[Pipeline] Summarizing new articles with Claude...")
    summarized = summarize_articles(new_articles)

    # Strip body after summarization
    summarized = strip_body(summarized)

    # Merge: new articles at the front (newest first)
    merged = summarized + existing

    # Deduplicate by ID (safety net)
    seen = set()
    deduped = []
    for a in merged:
        if a["id"] not in seen:
            seen.add(a["id"])
            deduped.append(a)

    # Cap total DB size
    if len(deduped) > MAX_TOTAL_ARTICLES:
        deduped = deduped[:MAX_TOTAL_ARTICLES]

    # Save
    save_articles(deduped)

    print(f"\n[Pipeline] Done! Added {len(summarized)} new articles.")
    print(f"[Pipeline] Total DB size: {len(deduped)} articles")
    print(f"[Pipeline] Finished at {datetime.utcnow().isoformat()}Z\n")


if __name__ == "__main__":
    initial = "--initial" in sys.argv
    run_pipeline(initial_run=initial)
