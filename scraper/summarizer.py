"""
GitHub Models Korean Summarizer
Summarizes English financial research articles into Korean (150 chars)
Uses GitHub Models API (OpenAI-compatible) — auth via GITHUB_TOKEN
"""

import os
import time
import re
from openai import OpenAI

GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com"
MODEL = "gpt-4o-mini"

client = OpenAI(
    base_url=GITHUB_MODELS_ENDPOINT,
    api_key=os.environ.get("GITHUB_TOKEN", ""),
)

SYSTEM_PROMPT = """당신은 글로벌 IB(투자은행) 리서치 전문 번역·요약가입니다.
영어로 된 금융 리서치 아티클을 한국어로 간결하게 요약하는 것이 역할입니다.
투자자와 금융 전문가를 대상으로 하며, 핵심 인사이트를 명확하고 전문적인 한국어로 표현합니다."""


def summarize_to_korean(title: str, body: str, source_name: str) -> str:
    """
    Summarize an article into Korean within ~150 characters.
    Returns Korean summary string.
    """

    content_for_summary = body.strip() if body.strip() else "(본문 없음 - 제목 기반 요약)"
    word_count = len(content_for_summary.split())

    if word_count > 600:
        content_for_summary = " ".join(content_for_summary.split()[:600]) + "..."

    prompt = f"""다음 {source_name} 리서치 아티클을 한국어로 요약해주세요.

**요약 규칙:**
- 150자 이내로 작성 (공백 포함)
- 핵심 투자 인사이트와 시장 전망에 집중
- 구체적인 수치나 전망이 있으면 포함
- 마침표로 끝나는 완전한 문장으로 작성
- 불필요한 수식어나 서론 없이 바로 핵심 내용 시작

**아티클 정보:**
제목: {title}
본문: {content_for_summary}

한국어 요약:"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        summary = response.choices[0].message.content.strip()

        # Clean up any markdown artifacts
        summary = re.sub(r"^\*+\s*", "", summary)
        summary = re.sub(r"\*+", "", summary)
        summary = summary.strip('"').strip("'")

        # Enforce 200 char limit (buffer over 150 for natural ending)
        if len(summary) > 200:
            truncated = summary[:200]
            last_period = truncated.rfind(".")
            if last_period > 100:
                summary = truncated[: last_period + 1]
            else:
                summary = truncated + "..."

        return summary

    except Exception as e:
        print(f"[Summarizer] Error for '{title}': {e}")
        return f"{source_name}의 최신 글로벌 금융 시장 분석 리포트입니다."


def summarize_articles(articles: list[dict], delay_seconds: float = 0.5) -> list[dict]:
    """
    Process a list of articles and add Korean summaries.
    Skips articles that already have a summary.
    """
    processed = 0
    for article in articles:
        if article.get("summary_ko") and len(article["summary_ko"]) > 10:
            continue  # Already summarized

        print(f"[Summarizer] Summarizing: {article['title'][:60]}...")
        article["summary_ko"] = summarize_to_korean(
            title=article["title"],
            body=article.get("body", ""),
            source_name=article["source_name"],
        )
        processed += 1

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    print(f"[Summarizer] Completed {processed} summaries")
    return articles
