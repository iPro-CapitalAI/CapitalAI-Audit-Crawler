# capitalai/audit/competitor.py
# Competitor Mode — wraps Crawl4AI's AsyncWebCrawler for multi-site audits.
# Crawl4AI handles: Playwright, JS rendering, markdown extraction, caching.
# We handle: deep-crawl orchestration, page limiting, SEO signal extraction.

import asyncio
import json
import re
from urllib.parse import urljoin, urlparse
from typing import Optional

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from capitalai.config.settings import (
    CLIENT_CRAWL_DEPTH, COMPETITOR_CRAWL_DEPTH,
    MAX_PAGES_CLIENT, MAX_PAGES_COMPETITOR,
    CRAWL4AI_HEADLESS, USER_AGENT
)

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def crawl_client(client_url: str, depth: int = CLIENT_CRAWL_DEPTH) -> dict:
    """Full crawl of the client site."""
    console.print(f"  [cyan]Crawling client:[/cyan] {client_url}")
    result = await _deep_crawl(client_url, max_pages=MAX_PAGES_CLIENT, depth=depth)
    console.print(f"  [green]✓ Client: {len(result)} pages[/green]")
    return result


async def crawl_competitors(competitor_urls: list[str], depth: int = COMPETITOR_CRAWL_DEPTH) -> dict:
    """Crawl up to 5 competitors concurrently (shallow — depth 2 default)."""
    all_data = {}
    tasks = [
        _deep_crawl(url, max_pages=MAX_PAGES_COMPETITOR, depth=depth)
        for url in competitor_urls[:5]
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for url, result in zip(competitor_urls, results):
        if isinstance(result, Exception):
            console.print(f"  [red]✗ Competitor failed: {url} — {result}[/red]")
            all_data[url] = {}
        else:
            all_data[url] = result
            console.print(f"  [green]✓ {url}: {len(result)} pages[/green]")

    return all_data


# ─────────────────────────────────────────────────────────────────────────────
# Internal — deep crawl via Crawl4AI
# ─────────────────────────────────────────────────────────────────────────────

async def _deep_crawl(base_url: str, max_pages: int, depth: int) -> dict:
    """
    Use Crawl4AI's AsyncWebCrawler to crawl a site up to `depth` levels.
    Returns {url: page_data_dict}.
    """
    domain = urlparse(base_url).netloc
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    results: dict = {}

    browser_cfg = BrowserConfig(
        headless=CRAWL4AI_HEADLESS,
        user_agent=USER_AGENT,
        verbose=False,
    )

    run_cfg = CrawlerRunConfig(
        word_count_threshold=50,
        exclude_external_links=False,
        process_iframes=False,
        remove_overlay_elements=True,
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        while queue and len(visited) < max_pages:
            url, current_depth = queue.pop(0)
            url = url.split("#")[0].rstrip("/") or url

            if url in visited:
                continue

            visited.add(url)

            try:
                crawl_result = await crawler.arun(url=url, config=run_cfg)

                if not crawl_result.success:
                    continue

                page_data = _extract_seo_signals(url, crawl_result)
                results[url] = page_data

                # Discover internal links for next depth level
                if current_depth < depth:
                    for link in (crawl_result.links.get("internal") or []):
                        href = link.get("href", "")
                        if href and urlparse(href).netloc == domain and href not in visited:
                            queue.append((href, current_depth + 1))

            except Exception as e:
                results[url] = {"url": url, "error": str(e)}

    return results


def _extract_seo_signals(url: str, crawl_result) -> dict:
    """
    Extract all SEO-relevant signals from a Crawl4AI CrawlResult.
    Crawl4AI already gives us clean markdown — we parse the raw HTML for schema/meta.
    """
    html = crawl_result.html or ""
    markdown = crawl_result.markdown or ""

    # ── Title ──
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    # ── Meta description ──
    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    meta_desc = meta_match.group(1).strip() if meta_match else ""

    # ── Canonical ──
    canonical_match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', html, re.IGNORECASE)
    canonical = canonical_match.group(1) if canonical_match else ""

    # ── Headings from markdown (Crawl4AI cleans these well) ──
    h1s = re.findall(r"^# (.+)$", markdown, re.MULTILINE)
    h2s = re.findall(r"^## (.+)$", markdown, re.MULTILINE)
    h3s = re.findall(r"^### (.+)$", markdown, re.MULTILINE)

    # ── Schema detection ──
    schema_types = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                t = data.get("@type")
                if t:
                    schema_types.append(t if isinstance(t, str) else t[0])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type"):
                        schema_types.append(item["@type"])
        except Exception:
            pass

    # ── Images missing alt ──
    all_imgs = re.findall(r"<img[^>]*>", html, re.IGNORECASE)
    missing_alt = sum(1 for img in all_imgs if 'alt=""' in img or "alt=''" in img or "alt=" not in img.lower())

    # ── Word count from markdown ──
    word_count = len(markdown.split())

    # ── Body excerpt (from clean markdown) ──
    body_excerpt = " ".join(markdown.split()[:200])

    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "canonical": canonical,
        "headings": {"h1": h1s, "h2": h2s, "h3": h3s},
        "schema_types": schema_types,
        "images_total": len(all_imgs),
        "images_missing_alt": missing_alt,
        "word_count": word_count,
        "body_excerpt": body_excerpt,
        "markdown_length": len(markdown),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Topic extraction helpers (used by gap analysis)
# ─────────────────────────────────────────────────────────────────────────────

def extract_topics(site_data: dict) -> list[str]:
    """Pull titles + H1s + H2s from any site data dict."""
    topics: set[str] = set()
    for page in site_data.values():
        if not isinstance(page, dict) or "error" in page:
            continue
        if page.get("title"):
            topics.add(page["title"].strip())
        for h in page.get("headings", {}).get("h1", []):
            if h.strip():
                topics.add(h.strip())
        for h in page.get("headings", {}).get("h2", []):
            if h.strip():
                topics.add(h.strip())
    return list(topics)


def extract_competitor_topics(competitor_data: dict) -> list[str]:
    """Merge topics from all competitor sites."""
    all_topics: set[str] = set()
    for site_data in competitor_data.values():
        all_topics.update(extract_topics(site_data))
    return list(all_topics)
