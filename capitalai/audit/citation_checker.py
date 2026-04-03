"""
CapitalAI — AI Citation Checker
================================
Checks whether a client domain is cited by:
  1. Perplexity.ai  — scraped headlessly via Playwright (no API needed)
  2. Grok (x.com)   — automated via your X Premium Plus browser session

Usage (standalone):
    python capitalai/audit/citation_checker.py --client https://leemingdanceworks.com --business "Leeming Dance Works" --location "Ottawa"

Usage (from pipeline):
    from capitalai.audit.citation_checker import check_ai_citations
    citations = await check_ai_citations(domain, business_name, location)

Returns:
    {
        "perplexity": [
            {"query": "dance school Ottawa", "cited": True,  "snippet": "..."},
            {"query": "kids dance classes Orleans", "cited": False, "snippet": None},
        ],
        "grok": [
            {"query": "dance school Ottawa", "cited": True,  "snippet": "..."},
        ],
        "summary": {
            "perplexity_cited": 1,
            "perplexity_total": 3,
            "grok_cited": 1,
            "grok_total": 2,
            "overall_verdict": "PARTIAL",   # CITED / PARTIAL / NOT CITED
        }
    }
"""

import asyncio
import re
import sys
import os
from pathlib import Path
from urllib.parse import urlparse, quote_plus

# ── path fix so module works standalone ───────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ── constants ─────────────────────────────────────────────────────────────────

# Where Grok stores your login session on Windows
# Playwright uses a persistent context so you stay logged in
GROK_SESSION_DIR = os.path.expanduser(
    r"~\AppData\Local\CapitalAI\grok-session"
)

PERPLEXITY_WAIT   = 8_000   # ms to wait for Perplexity answer to render
GROK_WAIT         = 12_000  # ms — Grok is slower
PAGE_TIMEOUT      = 30_000  # hard timeout per page


# ── query builder ─────────────────────────────────────────────────────────────

def build_queries(business_name: str, location: str, domain: str) -> dict:
    """
    Build 3 Perplexity queries and 2 Grok queries.
    Queries are intentionally generic — the kind a real customer would ask.
    """
    city = location.split(",")[0].strip()

    perplexity_queries = [
        f"best {_infer_category(domain)} in {city}",
        f"{_infer_category(domain)} {city} recommendations",
        f"top {_infer_category(domain)} {city}",
    ]

    grok_queries = [
        f"best {_infer_category(domain)} in {city}",
        f"{business_name} {city} — is it worth it?",
    ]

    return {"perplexity": perplexity_queries, "grok": grok_queries}


def _infer_category(domain: str) -> str:
    """
    Rough category inference from domain name keywords.
    Falls back to 'local business'.
    """
    d = domain.lower()
    mapping = {
        "dance": "dance school",
        "dental": "dental clinic",
        "dentist": "dental clinic",
        "law": "law firm",
        "lawyer": "law firm",
        "consult": "consulting firm",
        "plumb": "plumber",
        "electric": "electrician",
        "landscap": "landscaping company",
        "restaurant": "restaurant",
        "cafe": "cafe",
        "physio": "physiotherapy clinic",
        "chiro": "chiropractor",
        "yoga": "yoga studio",
        "gym": "gym",
        "fitness": "fitness studio",
        "realty": "real estate agent",
        "realtor": "real estate agent",
        "accountant": "accounting firm",
        "accounting": "accounting firm",
        "seo": "SEO agency",
        "marketing": "marketing agency",
    }
    for keyword, category in mapping.items():
        if keyword in d:
            return category
    return "local business"


# ── domain match helper ───────────────────────────────────────────────────────

def _domain_cited(text: str, domain: str) -> tuple[bool, str | None]:
    """
    Returns (cited: bool, snippet: str | None).
    Checks for bare domain, www variant, and business-name-like slug.
    """
    domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/")
    domain_clean = domain_clean.replace("www.", "")

    patterns = [
        re.escape(domain_clean),
        re.escape("www." + domain_clean),
    ]

    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 120)
            end   = min(len(text), match.end() + 120)
            snippet = "…" + text[start:end].strip() + "…"
            return True, snippet

    return False, None


# ── Perplexity checker ────────────────────────────────────────────────────────

async def _check_perplexity(
    domain: str,
    queries: list[str],
    headless: bool = True,
) -> list[dict]:
    """
    Submits each query to perplexity.ai and checks if domain is cited.
    Uses the public web interface — no API key needed.
    """
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        for query in queries:
            result = {"query": query, "cited": False, "snippet": None, "error": None}
            try:
                url = f"https://www.perplexity.ai/search?q={quote_plus(query)}"
                await page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")

                # Wait for the answer container to appear
                try:
                    await page.wait_for_selector(
                        '[class*="prose"], [class*="answer"], [data-testid*="answer"]',
                        timeout=PERPLEXITY_WAIT,
                    )
                except PWTimeout:
                    # Fall back — just wait a fixed time and grab whatever is there
                    await page.wait_for_timeout(PERPLEXITY_WAIT)

                text = await page.inner_text("body")
                cited, snippet = _domain_cited(text, domain)
                result["cited"]   = cited
                result["snippet"] = snippet

            except Exception as e:
                result["error"] = str(e)[:120]

            results.append(result)
            # polite delay between queries
            await asyncio.sleep(2)

        await browser.close()

    return results


# ── Grok checker ──────────────────────────────────────────────────────────────

async def _check_grok(
    domain: str,
    queries: list[str],
    session_dir: str = GROK_SESSION_DIR,
    headless: bool = True,
) -> list[dict]:
    """
    Uses a persistent Playwright browser context that holds your X/Grok login.

    FIRST-TIME SETUP (run once, not headless):
        Run with headless=False, log in to x.com manually in the browser
        that pops up, then close it. The session is saved to GROK_SESSION_DIR.
        All future runs use the saved session — no re-login needed.
    """
    results = []
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # Persistent context keeps cookies/localStorage between runs
        ctx = await pw.chromium.launch_persistent_context(
            str(session_path),
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        page = await ctx.new_page()

        # Check we're logged in
        await page.goto("https://x.com/i/grok", timeout=PAGE_TIMEOUT,
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        page_text = await page.inner_text("body")
        if "log in" in page_text.lower() or "sign in" in page_text.lower():
            results.append({
                "query": "SESSION_CHECK",
                "cited": False,
                "snippet": None,
                "error": (
                    "Not logged in to Grok. Run setup: "
                    "python -m capitalai.audit.citation_checker --setup-grok"
                ),
            })
            await ctx.close()
            return results

        for query in queries:
            result = {"query": query, "cited": False, "snippet": None, "error": None}
            try:
                # Navigate to Grok and submit query via the search box
                await page.goto("https://x.com/i/grok", timeout=PAGE_TIMEOUT,
                                wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Type into the Grok input
                input_sel = 'textarea, [contenteditable="true"], [placeholder*="Ask"]'
                await page.wait_for_selector(input_sel, timeout=10_000)
                await page.click(input_sel)
                await page.keyboard.type(query, delay=40)
                await page.keyboard.press("Enter")

                # Wait for response to stream in
                await page.wait_for_timeout(GROK_WAIT)

                text = await page.inner_text("body")
                cited, snippet = _domain_cited(text, domain)
                result["cited"]   = cited
                result["snippet"] = snippet

            except Exception as e:
                result["error"] = str(e)[:120]

            results.append(result)
            await asyncio.sleep(3)

        await ctx.close()

    return results


# ── summariser ────────────────────────────────────────────────────────────────

def _summarise(perplexity: list[dict], grok: list[dict]) -> dict:
    p_cited = sum(1 for r in perplexity if r.get("cited"))
    p_total = len([r for r in perplexity if not r.get("error")])

    g_cited = sum(1 for r in grok
                  if r.get("cited") and r.get("query") != "SESSION_CHECK")
    g_total = len([r for r in grok
                   if not r.get("error") and r.get("query") != "SESSION_CHECK"])

    total_cited = p_cited + g_cited
    total       = p_total + g_total

    if total == 0:
        verdict = "UNKNOWN"
    elif total_cited == 0:
        verdict = "NOT CITED"
    elif total_cited >= total * 0.5:
        verdict = "CITED"
    else:
        verdict = "PARTIAL"

    return {
        "perplexity_cited": p_cited,
        "perplexity_total": p_total,
        "grok_cited":       g_cited,
        "grok_total":       g_total,
        "overall_verdict":  verdict,
    }


# ── public entry point ────────────────────────────────────────────────────────

async def check_ai_citations(
    domain: str,
    business_name: str,
    location: str = "Ottawa",
    skip_grok: bool = False,
    headless: bool = True,
) -> dict:
    """
    Main function called from the audit pipeline.

    Args:
        domain:        client domain, e.g. "leemingdanceworks.com"
        business_name: e.g. "Leeming Dance Works"
        location:      e.g. "Ottawa" or "Ottawa, ON"
        skip_grok:     True if Grok session not set up yet
        headless:      False for debugging / first-time Grok setup
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "perplexity": [],
            "grok": [],
            "summary": {
                "perplexity_cited": 0, "perplexity_total": 0,
                "grok_cited": 0, "grok_total": 0,
                "overall_verdict": "SKIPPED — playwright not installed",
            },
        }

    queries = build_queries(business_name, location, domain)

    # Run Perplexity
    print("  Checking Perplexity citations...")
    perplexity_results = await _check_perplexity(
        domain, queries["perplexity"], headless=headless
    )
    for r in perplexity_results:
        status = "CITED" if r["cited"] else ("ERROR" if r.get("error") else "not cited")
        print(f"    [{status}] {r['query']}")

    # Run Grok
    grok_results = []
    if not skip_grok:
        print("  Checking Grok citations...")
        grok_results = await _check_grok(
            domain, queries["grok"], headless=headless
        )
        for r in grok_results:
            if r.get("query") == "SESSION_CHECK":
                print(f"    [SETUP NEEDED] {r.get('error', '')}")
            else:
                status = "CITED" if r["cited"] else ("ERROR" if r.get("error") else "not cited")
                print(f"    [{status}] {r['query']}")
    else:
        print("  Grok: skipped (use --setup-grok to enable)")

    summary = _summarise(perplexity_results, grok_results)
    print(f"  Verdict: {summary['overall_verdict']} "
          f"(Perplexity {summary['perplexity_cited']}/{summary['perplexity_total']}, "
          f"Grok {summary['grok_cited']}/{summary['grok_total']})")

    return {
        "perplexity": perplexity_results,
        "grok":       grok_results,
        "summary":    summary,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CapitalAI Citation Checker")
    parser.add_argument("--client",   required=False, help="Client URL")
    parser.add_argument("--business", required=False, help="Business name")
    parser.add_argument("--location", default="Ottawa", help="City/location")
    parser.add_argument("--skip-grok", action="store_true", help="Skip Grok check")
    parser.add_argument("--setup-grok", action="store_true",
                        help="Open browser to log in to X/Grok (run once)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show browser window (useful for debugging)")
    args = parser.parse_args()

    if args.setup_grok:
        async def _setup():
            session_path = Path(GROK_SESSION_DIR)
            session_path.mkdir(parents=True, exist_ok=True)
            async with async_playwright() as pw:
                ctx = await pw.chromium.launch_persistent_context(
                    str(session_path),
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--start-maximized",
                    ],
                    ignore_default_args=["--enable-automation"],
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )
                page = await ctx.new_page()

                # Hide webdriver property
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                """)

                await page.goto("https://x.com/login", wait_until="domcontentloaded")

                print("\n✓ Browser opened — x.com/login")
                print("  Log in manually in the browser window.")
                print("  Once logged in, navigate to x.com/i/grok to confirm Grok loads.")
                print("  Then CLOSE THE BROWSER — session saves automatically.\n")

                try:
                    await page.wait_for_event("close", timeout=300_000)
                except Exception:
                    pass
                await ctx.close()
            print("Session saved. Grok citations will work on next audit run.")
        asyncio.run(_setup())

    elif args.client:
        domain = urlparse(args.client).netloc or args.client
        domain = domain.replace("www.", "")
        business = args.business or domain.split(".")[0].replace("-", " ").title()

        results = asyncio.run(check_ai_citations(
            domain=domain,
            business_name=business,
            location=args.location,
            skip_grok=args.skip_grok,
            headless=not args.no_headless,
        ))

        print("\n── CITATION REPORT ──────────────────────────────")
        print(f"Domain:  {domain}")
        print(f"Verdict: {results['summary']['overall_verdict']}")
        print()
        print("Perplexity:")
        for r in results["perplexity"]:
            icon = "✓" if r["cited"] else "✗"
            print(f"  {icon} {r['query']}")
            if r["snippet"]:
                print(f"      {r['snippet'][:100]}")
            if r.get("error"):
                print(f"      ERROR: {r['error']}")
        print()
        print("Grok:")
        for r in results["grok"]:
            if r.get("query") == "SESSION_CHECK":
                print(f"  ! {r.get('error', 'Session issue')}")
                continue
            icon = "✓" if r["cited"] else "✗"
            print(f"  {icon} {r['query']}")
            if r["snippet"]:
                print(f"      {r['snippet'][:100]}")
    else:
        parser.print_help()