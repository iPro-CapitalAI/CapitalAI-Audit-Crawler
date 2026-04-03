#!/usr/bin/env python

import os
os.environ["PYTHONIOENCODING"] = "utf-8"
"""
CapitalAI Audit Crawler — CLI Entry Point

HOW TO RUN:
  python capitalai/run_audit.py --client https://capitalai.ca
  python capitalai/run_audit.py --client https://capitalai.ca --skip-eeat
  python capitalai/run_audit.py --client https://capitalai.ca --no-pdf
  python capitalai/run_audit.py --client https://capitalai.ca --no-email
  python capitalai/run_audit.py --client https://capitalai.ca --competitors https://comp1.ca

Default: generates Markdown + PDF + HTML email (all three).
"""

# ── Path fix — MUST be before all capitalai imports ───────────────────────────
import sys, os, asyncio
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from capitalai.audit.competitor import crawl_client, crawl_competitors
from capitalai.audit.gap_analysis import run_gap_analysis
from capitalai.audit.eeat_scorer import score_eeat
from capitalai.audit.technical import run_technical_audit
from capitalai.audit.citation_checker import check_ai_citations
from capitalai.output.markdown_writer import write_markdown_report
from capitalai.output.json_writer import write_json_report
from capitalai.config.settings import DEFAULT_MODEL, REPORTS_DIR

app     = typer.Typer(add_completion=False)
console = Console()


@app.command()
def audit(
    client: str = typer.Option(..., "--client", "-c",
        help="Client site URL (required)"),
    competitors: list[str] = typer.Option([], "--competitors", "--comp",
        help="Competitor URLs. Repeat flag for each. Max 5."),
    business: str = typer.Option("", "--business", "-b",
        help="Business name (for citation queries). Auto-inferred from domain if omitted."),
    location: str = typer.Option("Ottawa", "--location", "-l",
        help="City/location for citation queries (default: Ottawa)"),
    depth: int = typer.Option(None,
        help="Crawl depth (default: 3 client, 2 competitors)"),
    model: str = typer.Option(DEFAULT_MODEL,
        help="Ollama model (default: llama3.1:8b)"),
    output: str = typer.Option(REPORTS_DIR, "--output", "-o",
        help="Output directory"),
    skip_eeat: bool = typer.Option(False, "--skip-eeat",
        help="Skip Ollama E-E-A-T scoring (faster)"),
    skip_citations: bool = typer.Option(False, "--skip-citations",
        help="Skip AI citation check (Perplexity + Grok)"),
    skip_grok: bool = typer.Option(False, "--skip-grok",
        help="Skip Grok check only (use if Grok session not set up)"),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf",
        help="Generate PDF report (default: on)"),
    email: bool = typer.Option(True, "--email/--no-email",
        help="Generate HTML email report (default: on)"),
):
    """
    Run a full CapitalAI SEO audit.

    Outputs (all on by default):
      Markdown  — internal review version
      JSON      — 7-agent crew input
      PDF       — premium branded client deliverable
      HTML      — email-ready client version with CTA
    """
    asyncio.run(_run_audit_impl(
        client_url=client,
        competitor_urls=competitors,
        business_name=business,
        location=location,
        depth=depth,
        model=model,
        output_dir=output,
        skip_eeat=skip_eeat,
        skip_citations=skip_citations,
        skip_grok=skip_grok,
        gen_pdf=pdf,
        gen_email=email,
    ))


async def _run_audit_impl(client_url, competitor_urls, business_name, location,
                          depth, model, output_dir, skip_eeat, skip_citations,
                          skip_grok, gen_pdf, gen_email):
    """Main audit workflow implementation."""

    domain = urlparse(client_url).netloc
    if not business_name:
        business_name = domain.replace("www.", "").split(".")[0].replace("-", " ").title()

    console.print(f"[bold cyan]Starting Audit[/bold cyan]")
    console.print(f"[bold]Client:[/bold]   {client_url}")
    console.print(f"[bold]Business:[/bold] {business_name} · {location}")
    if competitor_urls:
        console.print(f"[bold]Competitors:[/bold] {', '.join(competitor_urls)}")
    console.print(f"[bold]Model:[/bold]    {model}")
    console.rule()

    total_steps = 7 + (1 if gen_pdf else 0) + (1 if gen_email else 0)
    if skip_citations:
        total_steps -= 1
    step = 0

    def _step(label):
        nonlocal step
        step += 1
        console.print(f"[bold yellow][{step}/{total_steps}][/bold yellow] {label}")

    # ── Crawl client ────────────────────────────────────────────────────────
    _step("Crawling client site...")
    client_data = await crawl_client(client_url, depth=depth or 3)

    # ── Crawl competitors ───────────────────────────────────────────────────
    competitor_data = {}
    if competitor_urls:
        _step("Crawling competitors...")
        competitor_data = await crawl_competitors(competitor_urls, depth=depth or 2)
    else:
        step += 1
        console.print(f"\n[dim][{step}/{total_steps}] No competitors — skipping.[/dim]")

    # ── AI Citation check ───────────────────────────────────────────────────
    citation_results = {
        "perplexity": [], "grok": [],
        "summary": {"overall_verdict": "SKIPPED",
                    "perplexity_cited": 0, "perplexity_total": 0,
                    "grok_cited": 0, "grok_total": 0},
    }
    if not skip_citations:
        _step("Checking AI citations (Perplexity + Grok)...")
        citation_results = await check_ai_citations(
            domain=domain,
            business_name=business_name,
            location=location,
            skip_grok=skip_grok,
        )
    else:
        step += 1
        console.print(f"\n[dim][{step}/{total_steps}] Citation check skipped (--skip-citations).[/dim]")

    # ── Gap analysis ────────────────────────────────────────────────────────
    _step("Running Ollama gap analysis...")
    gap_results = run_gap_analysis(client_data, competitor_data, model=model)

    # ── E-E-A-T scoring ─────────────────────────────────────────────────────
    eeat_scores = {
        "page_scores": {}, "site_aggregate": {},
        "pages_scored": 0, "total_pages_crawled": len(client_data)
    }
    if not skip_eeat:
        _step("Scoring E-E-A-T via Ollama...")
        eeat_scores = score_eeat(client_data, model=model)
    else:
        step += 1
        console.print(f"\n[dim][{step}/{total_steps}] E-E-A-T skipped (--skip-eeat).[/dim]")

    # ── Technical checks ────────────────────────────────────────────────────
    _step("Running technical SEO checks...")
    technical = run_technical_audit(client_data, model=model)

    # ── Markdown + JSON ─────────────────────────────────────────────────────
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

    # ── HTML + PDF ──────────────────────────────────────────────────────────
    # PDF writer generates HTML first, then renders it via Playwright.
    # HTML writer is called standalone only if PDF is disabled.
    pdf_path  = None
    html_path = None

    if gen_pdf:
        _step("Generating HTML + PDF report...")
        try:
            from capitalai.output.pdf_writer import write_pdf_report
            pdf_path = write_pdf_report(
                domain, client_data, competitor_data,
                gap_results, eeat_scores, technical, model, output_dir,
                citation_results=citation_results,
            )
            if pdf_path:
                html_path = pdf_path.replace("_audit.pdf", "_audit.html")
                console.print(f"  [green]OK[/green] PDF  → {pdf_path}")
                console.print(f"  [green]OK[/green] HTML → {html_path}")
        except Exception as e:
            console.print(f"  [red]PDF/HTML report failed: {e}[/red]")

    elif gen_email:
        # PDF disabled — generate HTML only
        _step("Generating HTML report...")
        try:
            from capitalai.output.html_email_writer import write_html_report
            html_path = write_html_report(
                domain, client_data, competitor_data,
                gap_results, eeat_scores, technical, model, output_dir,
                citation_results=citation_results,
            )
            console.print(f"  [green]OK[/green] {html_path}")
        except Exception as e:
            console.print(f"  [red]HTML report failed: {e}[/red]")

    # ── Summary ─────────────────────────────────────────────────────────────
    console.rule()
    console.print("[bold green]Audit Complete[/bold green]")
    console.print(f"[bold]Pages crawled[/bold]        {len(client_data)}")
    console.print(f"[bold]Competitors[/bold]          {len(competitor_data) if competitor_data else 0}")
    console.print(f"[bold]E-E-A-T Score[/bold]        {eeat_scores.get('site_aggregate', {}).get('overall_score', 'N/A')}/10")
    console.print(f"[bold]E-E-A-T Rating[/bold]       {eeat_scores.get('site_aggregate', {}).get('verdict', 'WEAK')}")
    console.print(f"[bold]Missing meta[/bold]         {technical.get('summary', {}).get('missing_meta', 0)}")
    console.print(f"[bold]No schema pages[/bold]      {technical.get('summary', {}).get('no_schema_pages', 0)}")
    console.print(f"[bold]Content gaps[/bold]         {len(gap_results.get('content_gaps', []))}")
    console.print(f"[bold]AI Citation verdict[/bold]  {citation_results['summary']['overall_verdict']}")
    console.print(f"  Perplexity: {citation_results['summary']['perplexity_cited']}/{citation_results['summary']['perplexity_total']} queries cited")
    console.print(f"  Grok:       {citation_results['summary']['grok_cited']}/{citation_results['summary']['grok_total']} queries cited")

    console.print("\n[bold]Markdown[/bold]             " + str(md_path))
    console.print("[bold]JSON[/bold]                 " + str(json_path))
    if pdf_path:
        console.print("[bold]PDF[/bold]                  " + str(pdf_path))
    if html_path:
        console.print("[bold]HTML Report[/bold]          " + str(html_path))

    console.print("\n[bold red]Human review required[/bold red] — E-E-A-T Guardian sign-off before client delivery.")

    console.print("\n[bold red]Human review required[/bold red] — E-E-A-T Guardian sign-off before client delivery.")


if __name__ == "__main__":
    app()