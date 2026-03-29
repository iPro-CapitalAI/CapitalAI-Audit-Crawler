# capitalai/audit/technical.py
# Deterministic technical SEO checks (no Ollama needed — rule-based).
# Checks: missing meta, duplicate/missing H1, missing alt, no schema,
#         thin content, missing canonical.

from capitalai.config.prompts import SCHEMA_OPPORTUNITY_PROMPT
from capitalai.audit.gap_analysis import call_ollama, parse_json_response
from capitalai.config.settings import DEFAULT_MODEL
from rich.console import Console

console = Console()

THIN_CONTENT_THRESHOLD = 300  # words


def run_technical_audit(client_data: dict, model: str = DEFAULT_MODEL) -> dict:
    """
    Run all deterministic technical checks.
    Returns structured findings dict.
    """
    issues = {
        "missing_meta_description": [],
        "missing_h1": [],
        "multiple_h1": [],
        "missing_alt_tags": [],
        "no_schema": [],
        "thin_content": [],
        "missing_canonical": [],
        "schema_opportunities": [],  # Ollama-assisted
    }

    pages_with_no_schema = []

    for url, page in client_data.items():
        if not isinstance(page, dict) or "error" in page:
            continue

        # Meta description
        if not page.get("meta_description", "").strip():
            issues["missing_meta_description"].append(url)

        # H1 checks
        h1s = page.get("headings", {}).get("h1", [])
        if len(h1s) == 0:
            issues["missing_h1"].append(url)
        elif len(h1s) > 1:
            issues["multiple_h1"].append({"url": url, "h1_count": len(h1s)})

        # Alt tags
        missing_alt = page.get("images_missing_alt", 0)
        if missing_alt > 0:
            issues["missing_alt_tags"].append({"url": url, "missing": missing_alt})

        # Schema
        if not page.get("schema_types"):
            issues["no_schema"].append(url)
            pages_with_no_schema.append(url)

        # Thin content
        if page.get("word_count", 0) < THIN_CONTENT_THRESHOLD:
            issues["thin_content"].append({
                "url": url,
                "word_count": page.get("word_count", 0)
            })

        # Canonical
        if not page.get("canonical", "").strip():
            issues["missing_canonical"].append(url)

    # Schema opportunities via Ollama (top 5 no-schema pages only)
    issues["schema_opportunities"] = _get_schema_opportunities(
        client_data, pages_with_no_schema[:5], model
    )

    # Summary counts
    issues["summary"] = {
        "missing_meta": len(issues["missing_meta_description"]),
        "h1_issues": len(issues["missing_h1"]) + len(issues["multiple_h1"]),
        "alt_tag_issues": sum(p["missing"] for p in issues["missing_alt_tags"]),
        "no_schema_pages": len(issues["no_schema"]),
        "thin_pages": len(issues["thin_content"]),
        "missing_canonical": len(issues["missing_canonical"]),
        "total_pages": len(client_data),
    }

    return issues


def _get_schema_opportunities(client_data: dict, urls: list[str], model: str) -> list[dict]:
    """Ask Ollama what schema to add to the highest-priority no-schema pages."""
    opportunities = []

    for url in urls:
        page = client_data.get(url, {})
        if not page or "error" in page:
            continue

        # Infer page category from URL path
        path = url.split("//", 1)[-1].split("/", 1)[-1] if "/" in url else "/"
        category = _infer_page_category(path, page.get("title", ""))

        prompt = SCHEMA_OPPORTUNITY_PROMPT.format(
            url=url,
            title=page.get("title", ""),
            existing_schema="None",
            page_category=category,
        )

        raw = call_ollama(prompt, model)
        result = parse_json_response(raw)
        if "parse_error" not in result:
            result["url"] = url
            opportunities.append(result)

    return opportunities


def _infer_page_category(path: str, title: str) -> str:
    """Simple heuristic to guess page type from path/title."""
    combined = (path + " " + title).lower()
    if any(w in combined for w in ["blog", "post", "article", "news"]):
        return "BlogPosting/Article"
    if any(w in combined for w in ["service", "solution", "offer"]):
        return "Service"
    if any(w in combined for w in ["about", "team", "story"]):
        return "AboutPage/Person"
    if any(w in combined for w in ["contact", "reach"]):
        return "ContactPage"
    if any(w in combined for w in ["faq", "question", "answer"]):
        return "FAQPage"
    if path in ("", "/", "home"):
        return "WebSite/LocalBusiness"
    return "WebPage"
