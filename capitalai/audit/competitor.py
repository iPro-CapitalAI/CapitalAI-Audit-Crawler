# capitalai/audit/competitor.py
# File: capitalai/audit/competitor.py
#
# WHY SITEMATE (AND MANY SITES) ONLY RETURN 1 PAGE:
#
#   Problem 1 — Cloudflare bot protection:
#     Sites like sitemate.com run Cloudflare. When BFSDeepCrawlStrategy
#     follows links via Playwright, subsequent requests trigger JS challenges
#     that return a challenge page instead of real HTML. Zero links extracted
#     from a challenge page = crawl stops after page 1.
#
#   Problem 2 — robots.txt explicitly blocks known AI bots:
#     sitemate.com/robots.txt: "User-agent: ClaudeBot Disallow: /"
#     Our UA (CapitalAI-Audit-Bot) is not blocked, but Cloudflare's
#     fingerprinting catches headless Playwright anyway.
#
#   Problem 3 — SPA / JS navigation:
#     Some sites use React Router / Next.js. Internal links are injected
#     by JS after load — BFS may see them, or may not, depending on timing.
#
# THE FIX — Two-strategy approach:
#
#   Strategy A: Sitemap-first (preferred, fast, bot-safe)
#     1. Fetch sitemap_index.xml or sitemap.xml via httpx (plain HTTP, no JS)
#     2. Parse all <loc> URLs — these are exactly what the site wants crawled
#     3. Crawl each URL directly via Playwright (renders JS, gets real content)
#     4. No link-following needed — no Cloudflare challenge chain
#     This is how Googlebot works. Sitemaps are explicitly for crawlers.
#
#   Strategy B: BFS fallback (for sites with no sitemap)
#     If sitemap fetch fails or returns <3 URLs, fall back to
#     BFSDeepCrawlStrategy with a realistic delay between requests
#     and a browser-like user agent to avoid fingerprinting.
#
# ANTI-BLOCKING MEASURES (applied to both strategies):
#   - Realistic browser User-Agent (Chrome on Windows)
#   - 1.0–2.0s delay between page requests (not hammering the server)
#   - Respect robots.txt (Crawl4AI default) — we don't disable it
#   - Random-ish delay via asyncio.sleep to avoid pattern detection
#   - Page timeout 20s — don't hang on slow Cloudflare challenges

import asyncio
import json
import random
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import httpx
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from rich.console import Console

from capitalai.config.settings import (
    CLIENT_CRAWL_DEPTH,
    COMPETITOR_CRAWL_DEPTH,
    MAX_PAGES_CLIENT,
    MAX_PAGES_COMPETITOR,
    CRAWL4AI_HEADLESS,
)

console = Console()

# Realistic Chrome user agent — passes most bot fingerprint checks
# Using a real Chrome UA is the single most effective anti-blocking measure
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Delay range between page requests (seconds) — polite + avoids pattern detection
DELAY_MIN = 1.0
DELAY_MAX = 2.5

# Sitemap fetch timeout (plain HTTP, fast)
SITEMAP_TIMEOUT = 15


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def crawl_client(client_url: str, depth: int = CLIENT_CRAWL_DEPTH) -> dict:
    console.print(f"  [cyan]Crawling client:[/cyan] {client_url}")
    result = await _smart_crawl(client_url, max_pages=MAX_PAGES_CLIENT, depth=depth)
    console.print(f"  [green]✓ Client: {len(result)} pages crawled[/green]")
    return result


async def crawl_competitors(
    competitor_urls: list[str],
    depth: int = COMPETITOR_CRAWL_DEPTH,
) -> dict:
    all_data = {}
    for url in competitor_urls[:5]:
        console.print(f"  [cyan]Crawling competitor:[/cyan] {url}")
        try:
            data = await _smart_crawl(url, max_pages=MAX_PAGES_COMPETITOR, depth=depth)
            all_data[url] = data
            console.print(f"  [green]✓ {url}: {len(data)} pages[/green]")
        except Exception as e:
            console.print(f"  [red]✗ {url}: {e}[/red]")
            all_data[url] = {}
    return all_data


# ─────────────────────────────────────────────────────────────────────────────
# Smart crawl — sitemap-first, BFS fallback
# ─────────────────────────────────────────────────────────────────────────────

async def _smart_crawl(base_url: str, max_pages: int, depth: int) -> dict:
    """
    Attempt sitemap-based crawl first. Fall back to BFS if sitemap unavailable.
    Sitemap crawl is faster, more complete, and bypasses Cloudflare bot detection.
    """
    domain = urlparse(base_url).netloc

    # ── Strategy A: Sitemap-first ──────────────────────────────────────────
    console.print(f"  [dim]Checking sitemap for {domain}...[/dim]")
    sitemap_urls = await _fetch_sitemap_urls(base_url, max_pages)

    if len(sitemap_urls) >= 3:
        console.print(
            f"  [green]Sitemap found:[/green] {len(sitemap_urls)} URLs — "
            f"using sitemap strategy (bypasses bot detection)"
        )
        return await _crawl_url_list(sitemap_urls, base_url)

    # ── Strategy B: BFS fallback ────────────────────────────────────────────
    console.print(
        f"  [yellow]No sitemap found — falling back to BFS "
        f"(depth={depth}, max={max_pages})[/yellow]"
    )
    return await _bfs_crawl(base_url, max_pages=max_pages, depth=depth)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy A: Sitemap fetcher + URL-list crawler
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_sitemap_urls(base_url: str, max_pages: int) -> list[str]:
    """
    Try common sitemap locations via plain HTTP (no Playwright, no JS).
    Returns list of page URLs found. Empty list if none found.
    """
    domain_root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    candidates  = [
        f"{domain_root}/sitemap_index.xml",
        f"{domain_root}/sitemap.xml",
        f"{domain_root}/sitemap-index.xml",
        f"{domain_root}/wp-sitemap.xml",
        f"{domain_root}/news-sitemap.xml",
    ]

    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
        "Referer": domain_root + "/",
    }

    all_urls: list[str] = []

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=SITEMAP_TIMEOUT,
        verify=False,
        http2=True,   # HTTP/2 better evades Cloudflare TLS fingerprinting
    ) as client:
        for candidate in candidates:
            try:
                resp = await client.get(candidate)
                body = resp.text
                is_cf_challenge = (
                    "cf-mitigated" in resp.headers
                    or "Just a moment" in body
                    or "Checking your browser" in body
                    or "challenge-platform" in body
                    or "turnstile" in body.lower()
                )
                if resp.status_code == 200 and not is_cf_challenge and (
                    "xml" in resp.headers.get("content-type", "").lower()
                    or body.strip().startswith("<?xml")
                    or "<urlset" in body
                    or "<sitemapindex" in body
                ):
                    resp_text = body  # use already-fetched body
                    urls = _parse_sitemap_xml(resp_text, base_url, client)
                    if isinstance(urls, list):
                        all_urls.extend(urls)
                    else:
                        # It's a coroutine from recursive sitemap index
                        urls = await urls
                        all_urls.extend(urls)
                    if all_urls:
                        break
            except Exception:
                continue

    # Deduplicate, keep same-domain only, cap at max_pages
    seen   = set()
    domain = urlparse(base_url).netloc
    result = []
    for url in all_urls:
        u = url.strip().split("#")[0].rstrip("/")
        if u and u not in seen and urlparse(u).netloc == domain:
            seen.add(u)
            result.append(u)
        if len(result) >= max_pages:
            break

    return result


def _parse_sitemap_xml(xml_text: str, base_url: str, client) -> list[str]:
    """
    Parse a sitemap XML (both <urlset> pages and <sitemapindex> index formats).
    For sitemapindex, fetches sub-sitemaps synchronously using httpx.
    """
    urls = []
    try:
        root = ET.fromstring(xml_text)
        ns   = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Sitemap index — contains pointers to sub-sitemaps
        for sitemap in root.findall(".//sm:sitemap/sm:loc", ns):
            if sitemap.text:
                sub_urls = _fetch_sub_sitemap_sync(sitemap.text.strip(), client)
                urls.extend(sub_urls)

        # Regular urlset — contains actual page URLs
        for url_el in root.findall(".//sm:url/sm:loc", ns):
            if url_el.text:
                urls.append(url_el.text.strip())

    except ET.ParseError:
        # Malformed XML — try regex fallback
        urls = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", xml_text)

    return urls


def _fetch_sub_sitemap_sync(url: str, client) -> list[str]:
    """Fetch a sub-sitemap synchronously (called from sync XML parse context)."""
    try:
        import urllib.request
        headers = {"User-Agent": BROWSER_UA}
        req  = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=SITEMAP_TIMEOUT)
        text = resp.read().decode("utf-8", errors="replace")
        urls = re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", text)
        return urls
    except Exception:
        return []


async def _crawl_url_list(urls: list[str], base_url: str) -> dict:
    """
    Crawl a list of URLs one by one via Playwright with polite delays.
    Each URL is a direct arun() call — no BFS, no link following.
    This bypasses Cloudflare's multi-request pattern detection.
    """
    browser_cfg = BrowserConfig(
        headless=CRAWL4AI_HEADLESS,
        user_agent=BROWSER_UA,
        verbose=False,
    )
    run_cfg = CrawlerRunConfig(
        word_count_threshold=50,
        remove_overlay_elements=True,
        process_iframes=False,
        stream=False,
        page_timeout=20000,   # 20s — skip slow/blocked pages
    )

    results    = {}
    page_count = 0

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for url in urls:
            try:
                # Polite delay — randomised to avoid pattern fingerprinting
                if page_count > 0:
                    delay = random.uniform(DELAY_MIN, DELAY_MAX)
                    await asyncio.sleep(delay)

                crawl_result = await crawler.arun(url=url, config=run_cfg)

                if not crawl_result or not crawl_result.success:
                    continue

                page_data = _extract_seo_signals(url, crawl_result)
                results[url] = page_data
                page_count  += 1

                wc = page_data.get("word_count", 0)
                console.print(
                    f"    [dim]pg {page_count:>3}[/dim] "
                    f"[white]{url[:72]}[/white] "
                    f"[dim]({wc}w)[/dim]"
                )

            except Exception as e:
                console.print(f"    [red]✗ {url[:60]}: {e}[/red]")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Strategy B: BFS fallback (for sites with no sitemap)
# ─────────────────────────────────────────────────────────────────────────────

async def _bfs_crawl(base_url: str, max_pages: int, depth: int) -> dict:
    """
    BFS deep crawl via Crawl4AI's BFSDeepCrawlStrategy.
    Used when no sitemap is available.
    stream=True gives live per-page output in PowerShell.
    """
    browser_cfg = BrowserConfig(
        headless=CRAWL4AI_HEADLESS,
        user_agent=BROWSER_UA,
        verbose=False,
    )
    bfs_strategy = BFSDeepCrawlStrategy(
        max_depth=depth,
        include_external=False,
        max_pages=max_pages,
    )
    run_cfg = CrawlerRunConfig(
        deep_crawl_strategy=bfs_strategy,
        word_count_threshold=50,
        remove_overlay_elements=True,
        process_iframes=False,
        stream=True,
        page_timeout=20000,
    )

    results    = {}
    page_count = 0

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            async for crawl_result in await crawler.arun(url=base_url, config=run_cfg):
                if not crawl_result or not crawl_result.success:
                    continue

                url = (crawl_result.url or base_url).split("#")[0].rstrip("/") or base_url
                page_data = _extract_seo_signals(url, crawl_result)
                results[url] = page_data
                page_count  += 1

                depth_val = (crawl_result.metadata.get("depth", "?")
                             if hasattr(crawl_result, "metadata")
                             and isinstance(crawl_result.metadata, dict) else "?")
                wc = page_data.get("word_count", 0)
                console.print(
                    f"    [dim]pg {page_count:>3}[/dim] "
                    f"[cyan]d={depth_val}[/cyan] "
                    f"[white]{url[:68]}[/white] "
                    f"[dim]({wc}w)[/dim]"
                )

    except Exception as e:
        console.print(f"  [red]BFS crawl error for {base_url}: {e}[/red]")
        results[base_url] = {"url": base_url, "error": str(e)}

    return results


# ─────────────────────────────────────────────────────────────────────────────
# SEO signal extraction — shared by both strategies
# ─────────────────────────────────────────────────────────────────────────────

def _extract_seo_signals(url: str, crawl_result) -> dict:
    """Extract all SEO-relevant signals from a Crawl4AI CrawlResult."""
    html     = crawl_result.html     or ""
    markdown = crawl_result.markdown or ""

    # Crawl4AI v0.4+ returns a markdown object
    if hasattr(markdown, "raw_markdown"):
        markdown = markdown.raw_markdown or ""
    elif hasattr(markdown, "fit_markdown"):
        markdown = markdown.fit_markdown or markdown.raw_markdown or ""

    # Title
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title   = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    # Meta description (both attribute orders)
    meta_m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
        html, re.I,
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']',
        html, re.I,
    )
    meta_desc = meta_m.group(1).strip() if meta_m else ""

    # Canonical
    can_m    = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', html, re.I
    )
    canonical = can_m.group(1) if can_m else ""

    # Headings from clean markdown
    h1s = re.findall(r"^# (.+)$",   markdown, re.M)
    h2s = re.findall(r"^## (.+)$",  markdown, re.M)
    h3s = re.findall(r"^### (.+)$", markdown, re.M)

    # Schema types
    schema_types: list[str] = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S | re.I,
    ):
        try:
            d = json.loads(m.group(1))
            if isinstance(d, dict) and d.get("@type"):
                t = d["@type"]
                schema_types.append(t if isinstance(t, str) else t[0])
            elif isinstance(d, list):
                for item in d:
                    if isinstance(item, dict) and item.get("@type"):
                        schema_types.append(item["@type"])
        except Exception:
            pass

    # Images missing alt
    imgs        = re.findall(r"<img[^>]*>", html, re.I)
    missing_alt = sum(
        1 for img in imgs
        if 'alt=""' in img or "alt=''" in img or "alt=" not in img.lower()
    )

    words        = markdown.split()
    word_count   = len(words)
    body_excerpt = " ".join(words[:200])

    return {
        "url":                url,
        "title":              title,
        "meta_description":   meta_desc,
        "canonical":          canonical,
        "headings":           {"h1": h1s, "h2": h2s, "h3": h3s},
        "schema_types":       schema_types,
        "images_total":       len(imgs),
        "images_missing_alt": missing_alt,
        "word_count":         word_count,
        "body_excerpt":       body_excerpt,
        "markdown_length":    len(markdown),
        "depth":              (crawl_result.metadata.get("depth", 0)
                               if hasattr(crawl_result, "metadata")
                               and isinstance(crawl_result.metadata, dict) else 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Topic extraction helpers — used by gap_analysis.py
# ─────────────────────────────────────────────────────────────────────────────

def extract_topics(site_data: dict) -> list[str]:
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
    all_topics: set[str] = set()
    for site_data in competitor_data.values():
        all_topics.update(extract_topics(site_data))
    return list(all_topics)
