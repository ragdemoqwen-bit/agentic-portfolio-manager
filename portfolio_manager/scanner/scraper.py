"""Playwright-based news scraper for Google Finance and Google News."""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ScrapedArticle:
    ticker: str
    headline: str
    source: str
    url: str
    snippet: str


def scrape_google_finance_news(ticker: str, max_articles: int = 10) -> list[ScrapedArticle]:
    """Scrape news headlines from Google Finance for a given ticker.

    Falls back gracefully if Playwright is not installed or the page is
    unreachable.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("Playwright not installed — skipping Google Finance scrape for %s", ticker)
        return []

    articles: list[ScrapedArticle] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            url = f"https://www.google.com/finance/quote/{ticker}:NASDAQ"
            page.goto(url, timeout=15_000, wait_until="domcontentloaded")

            # Try NYSE if NASDAQ returns no results
            if "We couldn't find" in (page.content() or ""):
                url = f"https://www.google.com/finance/quote/{ticker}:NYSE"
                page.goto(url, timeout=15_000, wait_until="domcontentloaded")

            news_items = page.query_selector_all("[data-article-url]")
            if not news_items:
                news_items = page.query_selector_all("div.yY3Lee")

            for item in news_items[:max_articles]:
                headline_el = item.query_selector("div.Yfwt5, a.TxRU9d")
                source_el = item.query_selector("div.sfyJob")
                link_el = item.query_selector("a[href]")

                headline = headline_el.inner_text().strip() if headline_el else ""
                source = source_el.inner_text().strip() if source_el else ""
                href = link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.google.com{href}"

                if headline:
                    articles.append(ScrapedArticle(
                        ticker=ticker,
                        headline=headline,
                        source=source,
                        url=href,
                        snippet="",
                    ))
            browser.close()
    except Exception as exc:
        log.warning("Google Finance scrape failed for %s: %s", ticker, exc)

    return articles


def scrape_google_news(query: str, max_articles: int = 10) -> list[ScrapedArticle]:
    """Scrape headlines from Google News search."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("Playwright not installed — skipping Google News scrape")
        return []

    articles: list[ScrapedArticle] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            search_url = f"https://news.google.com/search?q={query}%20stock&hl=en-US&gl=US&ceid=US%3Aen"
            page.goto(search_url, timeout=15_000, wait_until="domcontentloaded")

            items = page.query_selector_all("article")
            for item in items[:max_articles]:
                headline_el = item.query_selector("a.JtKRv, h3 a, h4 a")
                source_el = item.query_selector("div.vr1PYe, span.WSJvC")
                link_el = item.query_selector("a[href]")

                headline = headline_el.inner_text().strip() if headline_el else ""
                source = source_el.inner_text().strip() if source_el else ""
                href = link_el.get_attribute("href") if link_el else ""
                if href and href.startswith("./"):
                    href = f"https://news.google.com/{href[2:]}"

                if headline:
                    articles.append(ScrapedArticle(
                        ticker=query.upper(),
                        headline=headline,
                        source=source,
                        url=href,
                        snippet="",
                    ))
            browser.close()
    except Exception as exc:
        log.warning("Google News scrape failed for '%s': %s", query, exc)

    return articles


def scrape_news_for_ticker(ticker: str, max_per_source: int = 8) -> list[ScrapedArticle]:
    """Aggregate news from all scraped sources for a single ticker."""
    articles: list[ScrapedArticle] = []
    articles.extend(scrape_google_finance_news(ticker, max_per_source))
    articles.extend(scrape_google_news(ticker, max_per_source))

    # Deduplicate by headline similarity
    seen: set[str] = set()
    unique: list[ScrapedArticle] = []
    for a in articles:
        key = a.headline.lower().strip()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique
