# setup_capitalai_files.ps1
# Run this from your repo root:
# .\setup_capitalai_files.ps1
#
# This writes ALL capitalai source files directly to disk.
# Safe to re-run — overwrites existing files.

$root = Get-Location

# ── Ensure folders exist ──────────────────────────────────────────────────────
@(
    "capitalai",
    "capitalai\audit",
    "capitalai\config",
    "capitalai\output",
    "reports"
) | ForEach-Object {
    New-Item -ItemType Directory -Path $_ -Force | Out-Null
}

# ── __init__.py files ─────────────────────────────────────────────────────────
@(
    "capitalai\__init__.py",
    "capitalai\audit\__init__.py",
    "capitalai\config\__init__.py",
    "capitalai\output\__init__.py"
) | ForEach-Object {
    "" | Out-File -FilePath $_ -Encoding utf8 -Force
}

Write-Host "Folders and __init__ files ready." -ForegroundColor Green

# ── capitalai\config\settings.py ─────────────────────────────────────────────
@'
import os
from dotenv import load_dotenv
load_dotenv()

OLLAMA_BASE_URL         = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL           = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
CLIENT_CRAWL_DEPTH      = int(os.getenv("CLIENT_CRAWL_DEPTH", 3))
COMPETITOR_CRAWL_DEPTH  = int(os.getenv("COMPETITOR_CRAWL_DEPTH", 2))
MAX_PAGES_CLIENT        = int(os.getenv("MAX_PAGES_CLIENT", 150))
MAX_PAGES_COMPETITOR    = int(os.getenv("MAX_PAGES_COMPETITOR", 60))
MAX_COMPETITORS         = 5
CRAWL4AI_HEADLESS       = True
MAX_PAGES_TO_SCORE      = 12
EEAT_PRIORITY_PATHS     = ["/", "/about", "/about-us", "/services", "/contact", "/team", "/blog", "/pricing"]
REPORTS_DIR             = os.getenv("REPORTS_DIR", "reports")
USER_AGENT              = "CapitalAI-Audit-Bot/1.0 (+https://capitalai.ca/bot)"
'@ | Out-File -FilePath "capitalai\config\settings.py" -Encoding utf8 -Force

# ── capitalai\config\prompts.py ───────────────────────────────────────────────
@'
GAP_ANALYSIS_PROMPT = """
You are an expert SEO content strategist.

CLIENT TOPICS:
{client_topics}

COMPETITOR TOPICS (from {competitor_count} competitors):
{competitor_topics}

1. List topics competitors cover that the client does NOT (content gaps).
2. List topics only the client covers (unique strengths).
3. Suggest 5 high-priority new content opportunities.
One sentence max per item.

Return ONLY valid JSON, no markdown fences:
{{
  "content_gaps": ["gap1", "gap2"],
  "unique_strengths": ["strength1"],
  "content_opportunities": ["opp1", "opp2", "opp3", "opp4", "opp5"]
}}
"""

EEAT_SCORE_PROMPT = """
You are a Google E-E-A-T auditor. Score this page 0-10 on each dimension.

URL: {url}
TITLE: {title}
META: {meta_description}
HEADINGS: {headings}
CONTENT: {body_excerpt}
SCHEMA: {schema_types}

Return ONLY valid JSON, no markdown fences:
{{
  "experience": 0,
  "expertise": 0,
  "authoritativeness": 0,
  "trustworthiness": 0,
  "overall_score": 0.0,
  "top_issue": "one sentence",
  "quick_fix": "one sentence"
}}
"""

SCHEMA_OPPORTUNITY_PROMPT = """
You are a technical SEO schema expert.

URL: {url}
TITLE: {title}
EXISTING SCHEMA: {existing_schema}
PAGE TYPE: {page_category}

Return ONLY valid JSON, no markdown fences:
{{
  "missing_schema": ["Type1"],
  "priority_schema": "MostImportantType",
  "reason": "one sentence"
}}
"""
'@ | Out-File -FilePath "capitalai\config\prompts.py" -Encoding utf8 -Force

Write-Host "Config files written." -ForegroundColor Green

# ── capitalai\audit\gap_analysis.py ──────────────────────────────────────────
@'
import json, httpx
from rich.console import Console
from capitalai.config.settings import OLLAMA_BASE_URL, DEFAULT_MODEL
from capitalai.config.prompts import GAP_ANALYSIS_PROMPT

console = Console()

def _extract_topics(site_data: dict) -> list:
    topics = set()
    for page in site_data.values():
        if not isinstance(page, dict) or "error" in page:
            continue
        if page.get("title"):
            topics.add(page["title"].strip())
        for h in page.get("headings", {}).get("h1", []):
            if h.strip(): topics.add(h.strip())
        for h in page.get("headings", {}).get("h2", []):
            if h.strip(): topics.add(h.strip())
    return list(topics)

def _extract_competitor_topics(competitor_data: dict) -> list:
    all_topics = set()
    for site_data in competitor_data.values():
        all_topics.update(_extract_topics(site_data))
    return list(all_topics)

def call_ollama(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": {"temperature": 0.15, "num_predict": max_tokens}}
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")
    except httpx.ConnectError:
        console.print("[red]Ollama not running — start with: ollama serve[/red]")
        return ""
    except Exception as e:
        console.print(f"[red]Ollama error: {e}[/red]")
        return ""

def parse_json_response(raw: str, fallback_key: str = "raw") -> dict:
    if not raw:
        return {fallback_key: "", "parse_error": True}
    cleaned = raw.strip()
    if "```" in cleaned:
        for part in cleaned.split("```"):
            part = part.strip().lstrip("json").strip()
            try: return json.loads(part)
            except: continue
    try: return json.loads(cleaned)
    except:
        return {fallback_key: raw, "parse_error": True}

def run_gap_analysis(client_data: dict, competitor_data: dict, model: str = DEFAULT_MODEL) -> dict:
    client_topics = _extract_topics(client_data)
    competitor_topics = _extract_competitor_topics(competitor_data)
    if not competitor_topics:
        return {"content_gaps": [], "unique_strengths": client_topics[:15],
                "content_opportunities": [], "note": "No competitor data."}
    client_sample = "\n".join(f"- {t}" for t in client_topics[:80])
    comp_sample   = "\n".join(f"- {t}" for t in competitor_topics[:120])
    prompt = GAP_ANALYSIS_PROMPT.format(
        client_topics=client_sample,
        competitor_topics=comp_sample,
        competitor_count=len(competitor_data)
    )
    console.print(f"  [cyan]Ollama ({model}): gap analysis...[/cyan]")
    return parse_json_response(call_ollama(prompt, model))
'@ | Out-File -FilePath "capitalai\audit\gap_analysis.py" -Encoding utf8 -Force

# ── capitalai\audit\eeat_scorer.py ────────────────────────────────────────────
@'
import json
from rich.console import Console
from rich.progress import track
from capitalai.config.settings import DEFAULT_MODEL, MAX_PAGES_TO_SCORE, EEAT_PRIORITY_PATHS
from capitalai.config.prompts import EEAT_SCORE_PROMPT
from capitalai.audit.gap_analysis import call_ollama, parse_json_response

console = Console()

def score_eeat(client_data: dict, model: str = DEFAULT_MODEL) -> dict:
    pages = _select_priority_pages(client_data, MAX_PAGES_TO_SCORE)
    console.print(f"  [cyan]Scoring {len(pages)} pages for E-E-A-T...[/cyan]")
    page_scores = {}
    for url in track(pages, description="  E-E-A-T scoring"):
        page = client_data.get(url, {})
        if not page or "error" in page: continue
        prompt = EEAT_SCORE_PROMPT.format(
            url=url,
            title=page.get("title", ""),
            meta_description=page.get("meta_description", ""),
            headings=json.dumps({"h1": page.get("headings",{}).get("h1",[])[:3],
                                  "h2": page.get("headings",{}).get("h2",[])[:5]}),
            body_excerpt=page.get("body_excerpt","")[:800],
            schema_types=", ".join(page.get("schema_types",[])) or "None"
        )
        page_scores[url] = parse_json_response(call_ollama(prompt, model))
    agg = _aggregate(page_scores)
    return {"page_scores": page_scores, "site_aggregate": agg,
            "pages_scored": len(page_scores), "total_pages_crawled": len(client_data)}

def get_critical_pages(eeat_result: dict, threshold: float = 5.0) -> list:
    critical = []
    for url, scores in eeat_result.get("page_scores", {}).items():
        if "parse_error" not in scores:
            try:
                if float(scores.get("overall_score", 10)) < threshold:
                    critical.append({"url": url, "score": scores.get("overall_score"),
                                     "top_issue": scores.get("top_issue"),
                                     "quick_fix": scores.get("quick_fix")})
            except: pass
    return sorted(critical, key=lambda x: float(x.get("score") or 0))

def _select_priority_pages(client_data, max_pages):
    priority, normal = [], []
    for url in client_data.keys():
        path = "/" + url.split("//",1)[-1].split("/",1)[-1] if "/" in url else "/"
        if any(path == p or path.startswith(p+"/") for p in EEAT_PRIORITY_PATHS):
            priority.append(url)
        else:
            normal.append(url)
    normal.sort(key=lambda u: client_data.get(u,{}).get("word_count",0), reverse=True)
    return (priority + normal)[:max_pages]

def _aggregate(page_scores):
    dims = ["experience","expertise","authoritativeness","trustworthiness","overall_score"]
    totals = {d: 0.0 for d in dims}
    count = 0
    for scores in page_scores.values():
        if "parse_error" not in scores:
            for d in dims:
                try: totals[d] += float(scores.get(d, 0))
                except: pass
            count += 1
    if count == 0: return {"error": "No valid scores"}
    avg = {d: round(totals[d]/count, 1) for d in dims}
    avg["pages_scored"] = count
    o = avg["overall_score"]
    avg["rating"] = "STRONG" if o >= 7.5 else ("MODERATE" if o >= 5.0 else "WEAK")
    avg["verdict"] = ("Meets E-E-A-T standards." if o >= 7.5
                      else ("Meaningful gaps — add author bios and schema." if o >= 5.0
                            else "Immediate action required."))
    return avg
'@ | Out-File -FilePath "capitalai\audit\eeat_scorer.py" -Encoding utf8 -Force

# ── capitalai\audit\technical.py ──────────────────────────────────────────────
@'
from capitalai.config.prompts import SCHEMA_OPPORTUNITY_PROMPT
from capitalai.audit.gap_analysis import call_ollama, parse_json_response
from capitalai.config.settings import DEFAULT_MODEL

THIN = 300

def run_technical_audit(client_data: dict, model: str = DEFAULT_MODEL) -> dict:
    issues = {"missing_meta_description":[],"missing_h1":[],"multiple_h1":[],
              "missing_alt_tags":[],"no_schema":[],"thin_content":[],
              "missing_canonical":[],"schema_opportunities":[]}
    no_schema_urls = []
    for url, page in client_data.items():
        if not isinstance(page, dict) or "error" in page: continue
        if not page.get("meta_description","").strip():
            issues["missing_meta_description"].append(url)
        h1s = page.get("headings",{}).get("h1",[])
        if len(h1s)==0: issues["missing_h1"].append(url)
        elif len(h1s)>1: issues["multiple_h1"].append({"url":url,"h1_count":len(h1s)})
        m = page.get("images_missing_alt",0)
        if m > 0: issues["missing_alt_tags"].append({"url":url,"missing":m})
        if not page.get("schema_types"):
            issues["no_schema"].append(url)
            no_schema_urls.append(url)
        if page.get("word_count",0) < THIN:
            issues["thin_content"].append({"url":url,"word_count":page.get("word_count",0)})
        if not page.get("canonical","").strip():
            issues["missing_canonical"].append(url)
    issues["schema_opportunities"] = _schema_opps(client_data, no_schema_urls[:5], model)
    issues["summary"] = {
        "missing_meta": len(issues["missing_meta_description"]),
        "h1_issues": len(issues["missing_h1"])+len(issues["multiple_h1"]),
        "alt_tag_issues": sum(p["missing"] for p in issues["missing_alt_tags"]),
        "no_schema_pages": len(issues["no_schema"]),
        "thin_pages": len(issues["thin_content"]),
        "missing_canonical": len(issues["missing_canonical"]),
        "total_pages": len(client_data)
    }
    return issues

def _schema_opps(client_data, urls, model):
    opps = []
    for url in urls:
        page = client_data.get(url,{})
        if not page or "error" in page: continue
        path = url.split("//",1)[-1].split("/",1)[-1] if "/" in url else "/"
        cat = _infer(path, page.get("title",""))
        prompt = SCHEMA_OPPORTUNITY_PROMPT.format(
            url=url, title=page.get("title",""),
            existing_schema="None", page_category=cat)
        r = parse_json_response(call_ollama(prompt, model))
        if "parse_error" not in r:
            r["url"] = url
            opps.append(r)
    return opps

def _infer(path, title):
    c = (path+" "+title).lower()
    if any(w in c for w in ["blog","post","article"]): return "BlogPosting"
    if any(w in c for w in ["service","solution"]): return "Service"
    if any(w in c for w in ["about","team"]): return "AboutPage"
    if any(w in c for w in ["contact"]): return "ContactPage"
    if any(w in c for w in ["faq"]): return "FAQPage"
    return "WebPage"
'@ | Out-File -FilePath "capitalai\audit\technical.py" -Encoding utf8 -Force

Write-Host "Audit files written." -ForegroundColor Green

# ── capitalai\audit\competitor.py ─────────────────────────────────────────────
@'
import asyncio, json, re
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from rich.console import Console
from capitalai.config.settings import (
    CLIENT_CRAWL_DEPTH, COMPETITOR_CRAWL_DEPTH,
    MAX_PAGES_CLIENT, MAX_PAGES_COMPETITOR, CRAWL4AI_HEADLESS, USER_AGENT
)

console = Console()

async def crawl_client(client_url: str, depth: int = CLIENT_CRAWL_DEPTH) -> dict:
    console.print(f"  [cyan]Crawling client:[/cyan] {client_url}")
    result = await _deep_crawl(client_url, MAX_PAGES_CLIENT, depth)
    console.print(f"  [green]Client: {len(result)} pages[/green]")
    return result

async def crawl_competitors(competitor_urls: list, depth: int = COMPETITOR_CRAWL_DEPTH) -> dict:
    all_data = {}
    tasks = [_deep_crawl(url, MAX_PAGES_COMPETITOR, depth) for url in competitor_urls[:5]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for url, result in zip(competitor_urls, results):
        if isinstance(result, Exception):
            console.print(f"  [red]Failed: {url} - {result}[/red]")
            all_data[url] = {}
        else:
            all_data[url] = result
            console.print(f"  [green]{url}: {len(result)} pages[/green]")
    return all_data

async def _deep_crawl(base_url: str, max_pages: int, depth: int) -> dict:
    domain = urlparse(base_url).netloc
    visited = set()
    queue = [(base_url, 0)]
    results = {}
    browser_cfg = BrowserConfig(headless=CRAWL4AI_HEADLESS, user_agent=USER_AGENT, verbose=False)
    run_cfg = CrawlerRunConfig(word_count_threshold=50, process_iframes=False, remove_overlay_elements=True)
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        while queue and len(visited) < max_pages:
            url, cur_depth = queue.pop(0)
            url = url.split("#")[0].rstrip("/") or url
            if url in visited: continue
            visited.add(url)
            try:
                r = await crawler.arun(url=url, config=run_cfg)
                if not r.success: continue
                results[url] = _extract(url, r)
                if cur_depth < depth:
                    for link in (r.links.get("internal") or []):
                        href = link.get("href","")
                        if href and urlparse(href).netloc == domain and href not in visited:
                            queue.append((href, cur_depth+1))
            except Exception as e:
                results[url] = {"url": url, "error": str(e)}
    return results

def _extract(url, r) -> dict:
    html = r.html or ""
    md   = r.markdown or ""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I|re.S)
    title = re.sub(r"\s+"," ", title_m.group(1)).strip() if title_m else ""
    meta_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html, re.I)
    meta = meta_m.group(1).strip() if meta_m else ""
    can_m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', html, re.I)
    canonical = can_m.group(1) if can_m else ""
    h1s = re.findall(r"^# (.+)$", md, re.M)
    h2s = re.findall(r"^## (.+)$", md, re.M)
    h3s = re.findall(r"^### (.+)$", md, re.M)
    schema_types = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S|re.I):
        try:
            d = json.loads(m.group(1))
            if isinstance(d, dict) and d.get("@type"): schema_types.append(d["@type"])
            elif isinstance(d, list):
                for item in d:
                    if isinstance(item, dict) and item.get("@type"): schema_types.append(item["@type"])
        except: pass
    all_imgs = re.findall(r"<img[^>]*>", html, re.I)
    missing_alt = sum(1 for img in all_imgs if 'alt=""' in img or "alt=''" in img or "alt=" not in img.lower())
    body_excerpt = " ".join(md.split()[:200])
    return {"url":url,"title":title,"meta_description":meta,"canonical":canonical,
            "headings":{"h1":h1s,"h2":h2s,"h3":h3s},"schema_types":schema_types,
            "images_total":len(all_imgs),"images_missing_alt":missing_alt,
            "word_count":len(md.split()),"body_excerpt":body_excerpt}

def extract_topics(site_data: dict) -> list:
    topics = set()
    for page in site_data.values():
        if not isinstance(page, dict) or "error" in page: continue
        if page.get("title"): topics.add(page["title"].strip())
        for h in page.get("headings",{}).get("h1",[]): topics.add(h.strip())
        for h in page.get("headings",{}).get("h2",[]): topics.add(h.strip())
    return list(topics)
'@ | Out-File -FilePath "capitalai\audit\competitor.py" -Encoding utf8 -Force

Write-Host "competitor.py written." -ForegroundColor Green

# ── capitalai\output\markdown_writer.py ───────────────────────────────────────
@'
from datetime import datetime
from pathlib import Path

def write_markdown_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical, output_dir="reports"):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    fp = Path(output_dir) / f"{domain.replace('.','_')}_{ts}_audit.md"
    fp.parent.mkdir(parents=True, exist_ok=True)
    agg  = eeat_scores.get("site_aggregate", {})
    tech = technical.get("summary", {})
    lines = [
        f"# CapitalAI SEO Audit — {domain}",
        f"**Generated:** {datetime.now().strftime('%B %d, %Y %H:%M')}",
        f"**Status:** Requires E-E-A-T Guardian sign-off before client delivery",
        "---",
        "## Crawl Summary",
        f"| Metric | Value |",f"|--------|-------|",
        f"| Client pages | {len(client_data)} |",
        f"| Competitors | {len(competitor_data)} |",
        "---",
        "## E-E-A-T Site Score",
        f"**Rating:** {agg.get('rating','N/A')}",
        f"**Verdict:** {agg.get('verdict','')}",
        f"| Dimension | Score |",f"|-----------|-------|",
        f"| Experience | {agg.get('experience','?')} |",
        f"| Expertise | {agg.get('expertise','?')} |",
        f"| Authoritativeness | {agg.get('authoritativeness','?')} |",
        f"| Trustworthiness | {agg.get('trustworthiness','?')} |",
        f"| **Overall** | **{agg.get('overall_score','?')}** |",
        "---",
        "## Content Gap Analysis",
    ]
    for g in gap_results.get("content_gaps",[])[:15]: lines.append(f"- {g}")
    lines += ["### Top Content Opportunities"]
    for i,o in enumerate(gap_results.get("content_opportunities",[])[:5],1): lines.append(f"{i}. {o}")
    lines += ["---","## Technical Issues",
              f"| Issue | Count |",f"|-------|-------|",
              f"| Missing meta descriptions | {tech.get('missing_meta',0)} |",
              f"| H1 issues | {tech.get('h1_issues',0)} |",
              f"| Images missing alt | {tech.get('alt_tag_issues',0)} |",
              f"| Pages without schema | {tech.get('no_schema_pages',0)} |",
              f"| Thin content pages | {tech.get('thin_pages',0)} |",
              "---",
              "> Human review required before client delivery.",
              "*CapitalAI-Audit-Crawler*"]
    fp.write_text("\n".join(lines), encoding="utf-8")
    return str(fp)
'@ | Out-File -FilePath "capitalai\output\markdown_writer.py" -Encoding utf8 -Force

# ── capitalai\output\json_writer.py ───────────────────────────────────────────
@'
import json
from datetime import datetime
from pathlib import Path
from capitalai.audit.eeat_scorer import get_critical_pages

def write_json_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical, model="llama3.1:8b", output_dir="reports"):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    fp = Path(output_dir) / f"{domain.replace('.','_')}_{ts}_audit.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {"domain": domain, "generated_at": datetime.now().isoformat(),
                 "model": model, "human_review_required": True},
        "crawl_summary": {"client_pages": len(client_data), "competitors": len(competitor_data)},
        "eeat": {"site_aggregate": eeat_scores.get("site_aggregate",{}),
                 "page_scores": eeat_scores.get("page_scores",{})},
        "gap_analysis": gap_results,
        "technical": {"summary": technical.get("summary",{}),
                      "no_schema": technical.get("no_schema",[]),
                      "missing_meta": technical.get("missing_meta_description",[])},
        "agent_queue": _build_queue(eeat_scores, gap_results, technical)
    }
    fp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(fp)

def _build_queue(eeat_scores, gap_results, technical):
    queue = []
    for p in get_critical_pages(eeat_scores, 5.0):
        queue.append({"agent":"agent_eeat","priority":"HIGH","task":"improve_eeat",
                      "url":p["url"],"score":p["score"],"quick_fix":p["quick_fix"]})
    for g in gap_results.get("content_gaps",[])[:5]:
        queue.append({"agent":"agent_gap","priority":"MEDIUM","task":"create_content","topic":g})
    for url in technical.get("no_schema",[])[:5]:
        queue.append({"agent":"agent_schema","priority":"MEDIUM","task":"add_schema","url":url})
    return queue
'@ | Out-File -FilePath "capitalai\output\json_writer.py" -Encoding utf8 -Force

Write-Host "Output files written." -ForegroundColor Green

# ── capitalai\run_audit.py ────────────────────────────────────────────────────
@'
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
from capitalai.output.markdown_writer import write_markdown_report
from capitalai.output.json_writer import write_json_report
from capitalai.config.settings import DEFAULT_MODEL, REPORTS_DIR

app = typer.Typer(add_completion=False)
console = Console()

@app.command()
def audit(
    client: str = typer.Option(..., "--client", "-c"),
    competitors: list[str] = typer.Option([], "--competitors"),
    depth: int = typer.Option(None),
    model: str = typer.Option(DEFAULT_MODEL),
    output: str = typer.Option(REPORTS_DIR, "--output", "-o"),
    skip_eeat: bool = typer.Option(False, "--skip-eeat"),
):
    console.print(Panel.fit(
        f"[bold cyan]CapitalAI Audit Crawler[/bold cyan]\nClient: {client}\nModel: {model}",
        title="Starting Audit", border_style="cyan"))
    asyncio.run(_run(client, competitors, depth, model, output, skip_eeat))

async def _run(client_url, competitor_urls, depth, model, output_dir, skip_eeat):
    domain = urlparse(client_url).netloc
    console.print("\n[yellow][1/5][/yellow] Crawling client...")
    client_data = await crawl_client(client_url, depth=depth or 3)
    competitor_data = {}
    if competitor_urls:
        console.print("\n[yellow][2/5][/yellow] Crawling competitors...")
        competitor_data = await crawl_competitors(competitor_urls, depth=depth or 2)
    else:
        console.print("\n[dim][2/5] No competitors.[/dim]")
    console.print("\n[yellow][3/5][/yellow] Gap analysis...")
    gap_results = run_gap_analysis(client_data, competitor_data, model=model)
    eeat_scores = {"page_scores":{},"site_aggregate":{},"pages_scored":0,"total_pages_crawled":len(client_data)}
    if not skip_eeat:
        console.print("\n[yellow][4/5][/yellow] E-E-A-T scoring...")
        eeat_scores = score_eeat(client_data, model=model)
    else:
        console.print("\n[dim][4/5] E-E-A-T skipped.[/dim]")
    console.print("\n[yellow][4b][/yellow] Technical checks...")
    technical = run_technical_audit(client_data, model=model)
    console.print("\n[yellow][5/5][/yellow] Writing reports...")
    os.makedirs(output_dir, exist_ok=True)
    md   = write_markdown_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical, output_dir)
    jsn  = write_json_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical, model, output_dir)
    agg  = eeat_scores.get("site_aggregate", {})
    tech = technical.get("summary", {})
    t = Table(title="Audit Complete", border_style="green")
    t.add_column("Metric", style="bold"); t.add_column("Result")
    t.add_row("Pages crawled", str(len(client_data)))
    t.add_row("E-E-A-T Rating", agg.get("rating","Skipped"))
    t.add_row("Missing meta", str(tech.get("missing_meta",0)))
    t.add_row("No schema pages", str(tech.get("no_schema_pages",0)))
    t.add_row("Content gaps", str(len(gap_results.get("content_gaps",[]))))
    t.add_row("Markdown", md); t.add_row("JSON", jsn)
    console.print(t)
    console.print("\n[bold red]Human review required before client delivery.[/bold red]\n")

if __name__ == "__main__":
    app()
'@ | Out-File -FilePath "capitalai\run_audit.py" -Encoding utf8 -Force

Write-Host ""
Write-Host "All files written successfully." -ForegroundColor Green
Write-Host ""
Write-Host "Now run:" -ForegroundColor Cyan
Write-Host "  python capitalai/run_audit.py --client https://capitalai.ca --skip-eeat" -ForegroundColor White