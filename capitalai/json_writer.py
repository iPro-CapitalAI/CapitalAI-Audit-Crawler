# capitalai/output/json_writer.py
# Writes structured JSON for the 7-agent crew.
# Includes: crawl data (summary), E-E-A-T scores, gap analysis, agent task queue.

import json
from datetime import datetime
from pathlib import Path

from capitalai.audit.eeat_scorer import get_critical_pages


def write_json_report(
    domain: str,
    client_data: dict,
    competitor_data: dict,
    gap_results: dict,
    eeat_scores: dict,
    technical: dict,
    model: str = "llama3.1:8b",
    output_dir: str = "reports",
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_domain = domain.replace(".", "_").replace("/", "_")
    filepath = Path(output_dir) / f"{safe_domain}_{timestamp}_audit.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "meta": {
            "domain": domain,
            "generated_at": datetime.now().isoformat(),
            "crawler": "CapitalAI-Audit-Crawler / Crawl4AI fork",
            "model": model,
            "human_review_required": True,
            "version": "1.0.0",
        },
        "crawl_summary": {
            "client_pages": len(client_data),
            "competitors": len(competitor_data),
            "competitor_pages_total": sum(len(v) for v in competitor_data.values()),
        },
        "eeat": {
            "site_aggregate": eeat_scores.get("site_aggregate", {}),
            "page_scores": eeat_scores.get("page_scores", {}),
            "pages_scored": eeat_scores.get("pages_scored", 0),
        },
        "gap_analysis": gap_results,
        "technical": {
            "summary": technical.get("summary", {}),
            "missing_meta_description": technical.get("missing_meta_description", []),
            "missing_h1": technical.get("missing_h1", []),
            "multiple_h1": technical.get("multiple_h1", []),
            "no_schema": technical.get("no_schema", []),
            "thin_content": technical.get("thin_content", []),
            "schema_opportunities": technical.get("schema_opportunities", []),
        },
        "page_index": _build_page_index(client_data),
        "agent_queue": _build_agent_queue(eeat_scores, gap_results, technical),
    }

    filepath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(filepath)


def _build_page_index(client_data: dict) -> dict:
    """Compact page summaries — full text excluded to keep JSON lean."""
    index = {}
    for url, page in client_data.items():
        if isinstance(page, dict) and "error" not in page:
            index[url] = {
                "title": page.get("title", ""),
                "meta_description": page.get("meta_description", ""),
                "h1": page.get("headings", {}).get("h1", []),
                "word_count": page.get("word_count", 0),
                "schema_types": page.get("schema_types", []),
                "images_missing_alt": page.get("images_missing_alt", 0),
            }
    return index


def _build_agent_queue(eeat_scores: dict, gap_results: dict, technical: dict) -> list:
    """
    Pre-built task list for the 7-agent crew.
    Each task specifies: agent, priority, task_type, and target data.
    """
    queue = []
    priority_counter = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    # E-E-A-T agent — fix critical pages
    for page in get_critical_pages(eeat_scores, threshold=5.0):
        queue.append({
            "agent": "agent_eeat",
            "priority": "HIGH",
            "task_type": "improve_eeat",
            "url": page["url"],
            "current_score": page["score"],
            "top_issue": page["top_issue"],
            "quick_fix": page["quick_fix"],
        })
        priority_counter["HIGH"] += 1

    # Gap agent — create content for top gaps
    for gap in gap_results.get("content_gaps", [])[:5]:
        queue.append({
            "agent": "agent_gap",
            "priority": "MEDIUM",
            "task_type": "create_pillar_content",
            "topic": gap,
        })
        priority_counter["MEDIUM"] += 1

    # Schema agent — add markup to no-schema pages
    for opp in technical.get("schema_opportunities", []):
        queue.append({
            "agent": "agent_schema",
            "priority": "MEDIUM",
            "task_type": "add_schema",
            "url": opp.get("url"),
            "schema_type": opp.get("priority_schema"),
            "reason": opp.get("reason"),
        })
        priority_counter["MEDIUM"] += 1

    # Technical agent — meta + H1 + alt fixes
    for url in technical.get("missing_meta_description", [])[:10]:
        queue.append({
            "agent": "agent_technical",
            "priority": "HIGH",
            "task_type": "write_meta_description",
            "url": url,
        })
        priority_counter["HIGH"] += 1

    queue.append({
        "agent": "agent_reporter",
        "priority": "LOW",
        "task_type": "generate_client_report",
        "note": "Run after all HIGH priority tasks are complete and human-reviewed.",
    })

    return queue
