# capitalai/run_audit.py
# File: capitalai/run_audit.py
#
# ENCODING FIX:
#   Reconfigure sys.stdout/stderr to UTF-8 BEFORE any imports touch them.
#   This is the only reliable method on Windows PowerShell (CP1252 by default).
#   os.environ["PYTHONIOENCODING"] is too late — Python has already opened stdout.
#   Rich Console(force_terminal=True) keeps colour; safe=True would strip it.

import sys

# Reconfigure stdout/stderr to UTF-8 before anything else touches them.
# errors="replace" means any unencodable char becomes ? instead of crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

"""
CapitalAI Audit Crawler - CLI Entry Point

HOW TO RUN:
  python capitalai/run_audit.py --client https://capitalai.ca
  python capitalai/run_audit.py --client https://capitalai.ca --skip-eeat
  python capitalai/run_audit.py --client https://capitalai.ca --no-pdf
  python capitalai/run_audit.py --client https://capitalai.ca --no-email
  python capitalai/run_audit.py --client https://capitalai.ca --competitors https://comp1.ca

Default: generates Markdown + PDF + HTML email (all three).
"""

# ── Path fix — MUST be before all capitalai imports ───────────────────────────
import os, asyncio
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import typer
from rich.console import Console

from capitalai.audit.competitor import crawl_client, crawl_competitors
from capitalai.audit.gap_analysis import run_gap_analysis
from capitalai.audit.eeat_scorer import score_eeat
from capitalai.audit.technical import run_technical_audit
from capitalai.output.markdown_writer import write_markdown_report
from capitalai.output.json_writer import write_json_report
from capitalai.config.settings import DEFAULT_MODEL, REPORTS_DIR

app     = typer.Typer(add_completion=False)
# force_terminal=True keeps Rich colour markup active in PowerShell
console = Console(force_terminal=True)


def _safe(text) -> str:
    """Replace any non-ASCII characters with ASCII equivalents before printing.
    Prevents garbling on Windows PowerShell (CP1252 codepage).
    Handles common Unicode punctuation that Ollama frequently outputs."""
    if not isinstance(text, str):
        text = str(text)
    return (text
            .replace("—", "-")   # em dash
            .replace("–", "-")   # en dash
            .replace("‘", "'")   # left single quote
            .replace("’", "'")   # right single quote
            .replace("“", '"')   # left double quote
            .replace("”", '"')   # right double quote
            .replace("…", "...") # ellipsis
            .replace("â", "")    # common UTF-8 mangling artifact
            .encode("ascii", "replace").decode("ascii")
            )


@app.command()
def audit(
    client: str = typer.Option(..., "--client", "-c",
        help="Client site URL (required)"),
    competitors: list[str] = typer.Option([], "--competitors", "--comp",
        help="Competitor URLs. Repeat flag for each. Max 5."),
    depth: int = typer.Option(None,
        help="Crawl depth (default: 3 client, 2 competitors)"),
    model: str = typer.Option(DEFAULT_MODEL,
        help="Ollama model (default: llama3.1:8b)"),
    output: str = typer.Option(REPORTS_DIR, "--output", "-o",
        help="Output directory"),
    skip_eeat: bool = typer.Option(False, "--skip-eeat",
        help="Skip Ollama E-E-A-T scoring (faster)"),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf",
        help="Generate PDF report (default: on)"),
    email: bool = typer.Option(True, "--email/--no-email",
        help="Generate HTML email report (default: on)"),
):
    """
    Run a full CapitalAI SEO audit.

    Outputs (all on by default):
      Markdown  - internal review version
      JSON      - 7-agent crew input
      PDF       - premium branded client deliverable
      HTML      - dashboard-style client report
    """
    asyncio.run(_run_audit(
        client_url=client,
        competitor_urls=competitors,
        depth=depth,
        model=model,
        output_dir=output,
        skip_eeat=skip_eeat,
        gen_pdf=pdf,
        gen_email=email,
    ))


async def _run_audit(
    client_url, competitor_urls, depth, model,
    output_dir, skip_eeat, gen_pdf, gen_email
):
    """Main audit workflow - single definition, no duplicates."""

    # ── Startup banner ────────────────────────────────────────────────────────
    console.print()
    console.print("[bold cyan]CapitalAI Audit Crawler[/bold cyan]")
    console.print(f"  [bold]Client:[/bold]      {client_url}")
    if competitor_urls:
        console.print(f"  [bold]Competitors:[/bold] {', '.join(competitor_urls)}")
    else:
        console.print("  [bold]Competitors:[/bold] None")
    console.print(f"  [bold]Model:[/bold]       {model}")
    console.print(f"  [bold]Outputs:[/bold]     MD + JSON + PDF + HTML")
    console.print("-" * 60)

    domain      = urlparse(client_url).netloc
    total_steps = 6 + (1 if gen_pdf else 0) + (1 if gen_email else 0)
    step        = 0

    def _step(label):
        nonlocal step
        step += 1
        console.print(f"[bold yellow][{step}/{total_steps}][/bold yellow] {label}")

    # ── Crawl client ──────────────────────────────────────────────────────────
    _step("Crawling client site...")
    client_data = await crawl_client(client_url, depth=depth or 3)

    # ── Crawl competitors ─────────────────────────────────────────────────────
    competitor_data = {}
    if competitor_urls:
        _step("Crawling competitors...")
        competitor_data = await crawl_competitors(competitor_urls, depth=depth or 2)
    else:
        step += 1
        console.print(f"[dim][{step}/{total_steps}] No competitors - skipping.[/dim]")

    # ── Gap analysis ──────────────────────────────────────────────────────────
    _step("Running Ollama gap analysis...")
    gap_results = run_gap_analysis(client_data, competitor_data, model=model)

    # ── E-E-A-T scoring ───────────────────────────────────────────────────────
    eeat_scores = {
        "page_scores": {}, "site_aggregate": {},
        "pages_scored": 0, "total_pages_crawled": len(client_data),
    }
    if not skip_eeat:
        _step("Scoring E-E-A-T via Ollama...")
        eeat_scores = score_eeat(client_data, model=model)
    else:
        step += 1
        console.print(f"[dim][{step}/{total_steps}] E-E-A-T skipped (--skip-eeat).[/dim]")

    # ── Technical checks ──────────────────────────────────────────────────────
    _step("Running technical SEO checks...")
    technical = run_technical_audit(client_data, model=model)

    # ── Markdown + JSON ───────────────────────────────────────────────────────
    _step("Writing Markdown + JSON reports...")
    os.makedirs(output_dir, exist_ok=True)

    md_path = write_markdown_report(
        domain, client_data, competitor_data,
        gap_results, eeat_scores, technical, output_dir
    )
    json_path = write_json_report(
        domain, client_data, competitor_data,
        gap_results, eeat_scores, technical, model, output_dir
    )

    # ── PDF ───────────────────────────────────────────────────────────────────
    pdf_path = None
    if gen_pdf:
        _step("Generating PDF report...")
        try:
            from capitalai.output.pdf_writer import write_pdf_report
            pdf_path = write_pdf_report(
                domain, client_data, competitor_data,
                gap_results, eeat_scores, technical, model, output_dir
            )
            console.print(f"  [green]OK[/green] {pdf_path}")
        except ImportError:
            console.print(
                "  [yellow]PDF skipped - reportlab not installed.[/yellow]\n"
                "  Run: [cyan]pip install reportlab[/cyan]"
            )
        except Exception as e:
            console.print(f"  [red]PDF failed: {e}[/red]")

    # ── HTML report ───────────────────────────────────────────────────────────
    html_path = None
    if gen_email:
        _step("Generating HTML report...")
        try:
            from capitalai.output.html_email_writer import write_html_report
            html_path = write_html_report(
                domain, client_data, competitor_data,
                gap_results, eeat_scores, technical, model, output_dir
            )
            console.print(f"  [green]OK[/green] {html_path}")
        except Exception as e:
            console.print(f"  [red]HTML report failed: {e}[/red]")

    # ── Summary table ─────────────────────────────────────────────────────────
    console.print("-" * 60)
    console.print("[bold green]Audit Complete[/bold green]")
    console.print()

    agg  = eeat_scores.get("site_aggregate", {})
    tech = technical.get("summary", {})
    gaps = gap_results.get("content_gaps", [])

    # Plain text summary — no Unicode box characters, no emojis
    rows = [
        ("Pages crawled",    str(len(client_data))),
        ("Competitors",      str(len(competitor_data) if competitor_data else 0)),
        ("E-E-A-T Score",    f"{agg.get('overall_score', 'N/A')}/10"),
        ("E-E-A-T Rating",   _safe(agg.get("rating", "N/A"))),
        ("Missing meta",     str(tech.get("missing_meta", 0))),
        ("No schema pages",  str(tech.get("no_schema_pages", 0))),
        ("Content gaps",     str(len(gaps))),
        ("---",              "---"),
        ("Markdown",         _safe(str(md_path))),
        ("JSON",             _safe(str(json_path))),
    ]
    if pdf_path:
        rows.append(("PDF", _safe(str(pdf_path))))
    if html_path:
        rows.append(("HTML Report", _safe(str(html_path))))

    for label, value in rows:
        if label == "---":
            console.print()
            continue
        console.print(f"  [bold]{label:<18}[/bold] {_safe(value)}")

    console.print()
    console.print("[bold red]Human review required[/bold red] - E-E-A-T Guardian sign-off before client delivery.")
    console.print()


if __name__ == "__main__":
    app()