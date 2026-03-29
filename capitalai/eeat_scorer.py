# capitalai/audit/eeat_scorer.py
# E-E-A-T scoring for key client pages via Ollama.
# Scores top N pages (priority: homepage, about, services, blog).
# Produces per-page scores + site-level aggregate + traffic-light rating.

import json
from rich.console import Console
from rich.progress import track

from capitalai.config.settings import DEFAULT_MODEL, MAX_PAGES_TO_SCORE, EEAT_PRIORITY_PATHS
from capitalai.config.prompts import EEAT_SCORE_PROMPT
from capitalai.audit.gap_analysis import call_ollama, parse_json_response

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_eeat(client_data: dict, model: str = DEFAULT_MODEL) -> dict:
    """
    Score E-E-A-T for up to MAX_PAGES_TO_SCORE priority pages.
    Returns: {page_scores, site_aggregate, pages_scored, total_pages_crawled}
    """
    pages_to_score = _select_priority_pages(client_data, MAX_PAGES_TO_SCORE)
    console.print(f"  [cyan]Scoring {len(pages_to_score)} pages for E-E-A-T via Ollama...[/cyan]")

    page_scores = {}

    for url in track(pages_to_score, description="  E-E-A-T scoring"):
        page = client_data.get(url, {})
        if not page or "error" in page:
            continue

        prompt = EEAT_SCORE_PROMPT.format(
            url=url,
            title=page.get("title", ""),
            meta_description=page.get("meta_description", ""),
            headings=json.dumps({
                "h1": page.get("headings", {}).get("h1", [])[:3],
                "h2": page.get("headings", {}).get("h2", [])[:6],
            }),
            body_excerpt=page.get("body_excerpt", "")[:800],
            schema_types=", ".join(page.get("schema_types", [])) or "None detected",
        )

        raw = call_ollama(prompt, model)
        scores = parse_json_response(raw)
        page_scores[url] = scores

    aggregate = _aggregate_scores(page_scores)

    return {
        "page_scores": page_scores,
        "site_aggregate": aggregate,
        "pages_scored": len(page_scores),
        "total_pages_crawled": len(client_data),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _select_priority_pages(client_data: dict, max_pages: int) -> list[str]:
    """
    Prioritize pages that matter most for E-E-A-T:
    1. Pages matching EEAT_PRIORITY_PATHS (home, about, services, etc.)
    2. Then remaining pages sorted by word count (longest = most content)
    """
    all_urls = list(client_data.keys())
    priority, normal = [], []

    for url in all_urls:
        path = "/" + url.split("//", 1)[-1].split("/", 1)[-1] if "/" in url else "/"
        if any(path == p or path.startswith(p + "/") for p in EEAT_PRIORITY_PATHS):
            priority.append(url)
        else:
            normal.append(url)

    # Sort normal pages by word count descending
    normal.sort(
        key=lambda u: client_data.get(u, {}).get("word_count", 0),
        reverse=True
    )

    return (priority + normal)[:max_pages]


def _aggregate_scores(page_scores: dict) -> dict:
    """Average E-E-A-T scores across all successfully scored pages."""
    dims = ["experience", "expertise", "authoritativeness", "trustworthiness", "overall_score"]
    totals = {d: 0.0 for d in dims}
    count = 0

    for url, scores in page_scores.items():
        if "parse_error" not in scores:
            for d in dims:
                try:
                    totals[d] += float(scores.get(d, 0))
                except (TypeError, ValueError):
                    pass
            count += 1

    if count == 0:
        return {"error": "No valid scores — check Ollama is running"}

    averages = {d: round(totals[d] / count, 1) for d in dims}
    averages["pages_scored"] = count

    overall = averages["overall_score"]
    if overall >= 7.5:
        averages["rating"] = "🟢 STRONG"
        averages["verdict"] = "Site meets E-E-A-T standards. Focus on amplification."
    elif overall >= 5.0:
        averages["rating"] = "🟡 MODERATE"
        averages["verdict"] = "Meaningful E-E-A-T gaps. Prioritize author bios, schema, and trust signals."
    else:
        averages["rating"] = "🔴 WEAK"
        averages["verdict"] = "Immediate action required. High risk under Google Helpful Content."

    return averages


def get_critical_pages(eeat_result: dict, threshold: float = 5.0) -> list[dict]:
    """Return pages scoring below threshold — for agent priority queue."""
    critical = []
    for url, scores in eeat_result.get("page_scores", {}).items():
        if "parse_error" not in scores:
            try:
                if float(scores.get("overall_score", 10)) < threshold:
                    critical.append({
                        "url": url,
                        "score": scores.get("overall_score"),
                        "top_issue": scores.get("top_issue"),
                        "quick_fix": scores.get("quick_fix"),
                    })
            except (TypeError, ValueError):
                pass
    return sorted(critical, key=lambda x: float(x["score"] or 0))
