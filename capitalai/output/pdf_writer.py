# capitalai/output/pdf_writer.py
"""
CapitalAI PDF Writer — Playwright HTML-to-PDF
==============================================
Renders the HTML audit report to a pixel-perfect PDF using headless Chromium.
This replaces the old ReportLab writer entirely.

Why Playwright instead of ReportLab:
- The HTML report already looks great — this captures it exactly
- No separate layout code to maintain
- Handles tables, colours, fonts, progress bars, everything
- Output looks identical to what the client sees in a browser

Requirements:
- playwright (already installed for citation checker)
- The HTML report must be generated first (html_email_writer.py)
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


async def _html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """
    Render an HTML file to PDF using headless Chromium.
    Returns True on success, False on failure.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Load the HTML file directly from disk
        file_url = Path(html_path).resolve().as_uri()
        await page.goto(file_url, wait_until="networkidle", timeout=30_000)

        # Let fonts and animations settle
        await page.wait_for_timeout(1500)

        # Inject print-specific CSS overrides:
        # - Hide sidebar (not useful in PDF)
        # - Force full-width layout
        # - Remove sticky positioning
        # - Ensure colours print (not greyed out by browser)
        await page.add_style_tag(content="""
            @media print {
                * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
            }
            .sidebar { display: none !important; }
            .shell { display: block !important; max-width: 100% !important; box-shadow: none !important; }
            .main { width: 100% !important; }
            .topbar { position: static !important; }
            .gate { display: none !important; }
            .card:hover { transform: none !important; box-shadow: none !important; }
            body { background: #fff !important; }
        """)

        await page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={
                "top":    "16mm",
                "bottom": "16mm",
                "left":   "14mm",
                "right":  "14mm",
            },
        )

        await browser.close()
    return True


def write_pdf_report(
    domain: str,
    client_data: dict,
    competitor_data: dict,
    gap_results: dict,
    eeat_scores: dict,
    technical: dict,
    model: str = "llama3.1:8b",
    output_dir: str = "reports",
    citation_results: dict | None = None,
) -> str | None:
    """
    Generate the HTML report first, then render it to PDF via Playwright.

    This is a drop-in replacement for the old ReportLab pdf_writer.
    Called from run_audit.py exactly as before.
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("  PDF skipped — playwright not installed.")
        print("  Run: pip install playwright --break-system-packages")
        print("       playwright install chromium")
        return None

    # ── Step 1: Generate the HTML report ──────────────────────────────────────
    try:
        from capitalai.output.html_email_writer import write_html_report
    except ImportError:
        print("  PDF skipped — html_email_writer not found.")
        return None

    html_path = write_html_report(
        domain=domain,
        client_data=client_data,
        competitor_data=competitor_data,
        gap_results=gap_results,
        eeat_scores=eeat_scores,
        technical=technical,
        model=model,
        output_dir=output_dir,
        citation_results=citation_results or {},
    )

    # ── Step 2: Render HTML → PDF ──────────────────────────────────────────────
    pdf_path = html_path.replace("_audit.html", "_audit.pdf")

    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # Already inside a running loop (called from run_audit.py)
            # Use a thread to run the coroutine without conflicting
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _html_to_pdf(html_path, pdf_path))
                success = future.result(timeout=60)
        except RuntimeError:
            # No running loop — call directly
            success = asyncio.run(_html_to_pdf(html_path, pdf_path))

        if success:
            return pdf_path
        else:
            print("  PDF rendering failed.")
            return None
    except Exception as e:
        print(f"  PDF rendering error: {e}")
        return None


# ── CLI — convert any HTML report to PDF directly ─────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CapitalAI HTML → PDF converter")
    parser.add_argument("html", help="Path to HTML audit report")
    parser.add_argument("--out", help="Output PDF path (default: same as HTML)")
    args = parser.parse_args()

    html_path = args.html
    pdf_path  = args.out or html_path.replace(".html", ".pdf")

    print(f"Converting: {html_path}")
    print(f"Output:     {pdf_path}")

    success = asyncio.run(_html_to_pdf(html_path, pdf_path))
    if success:
        print(f"Done: {pdf_path}")
    else:
        print("Failed.")
        sys.exit(1)