# capitalai/output/markdown_writer.py
# Writes the final audit report as clean Markdown.
# Designed for: (1) human E-E-A-T Guardian review, (2) client delivery.

from datetime import datetime
from pathlib import Path


def write_markdown_report(
    domain: str,
    client_data: dict,
    competitor_data: dict,
    gap_results: dict,
    eeat_scores: dict,
    technical: dict,
    output_dir: str = "reports",
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_domain = domain.replace(".", "_").replace("/", "_")
    filepath = Path(output_dir) / f"{safe_domain}_{timestamp}_audit.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = _build_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical)
    filepath.write_text("\n".join(lines), encoding="utf-8")
    return str(filepath)


# ─────────────────────────────────────────────────────────────────────────────

def _build_report(domain, client_data, competitor_data, gap_results, eeat_scores, technical):
    now = datetime.now().strftime("%B %d, %Y at %H:%M")
    agg = eeat_scores.get("site_aggregate", {})
    tech_summary = technical.get("summary", {})

    lines = [
        f"# CapitalAI SEO Audit — {domain}",
        f"",
        f"**Generated:** {now}  ",
        f"**Tool:** CapitalAI-Audit-Crawler (Crawl4AI + Ollama llama3.1:8b)  ",
        f"**Status:** ⚠️ Requires E-E-A-T Guardian sign-off before client delivery",
        "",
        "---",
        "",
        "## 📊 Crawl Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Client pages crawled | {len(client_data)} |",
        f"| Competitors analyzed | {len(competitor_data)} |",
        f"| Competitor pages total | {sum(len(v) for v in competitor_data.values())} |",
        f"| Pages scored for E-E-A-T | {eeat_scores.get('pages_scored', 0)} |",
        "",
        "---",
        "",
        "## 🏆 E-E-A-T Site Score",
        "",
        f"**Rating:** {agg.get('rating', 'N/A')}",
        f"**Verdict:** {agg.get('verdict', '')}",
        "",
        "| Dimension | Score /10 |",
        "|-----------|-----------|",
        f"| Experience | {agg.get('experience', '?')} |",
        f"| Expertise | {agg.get('expertise', '?')} |",
        f"| Authoritativeness | {agg.get('authoritativeness', '?')} |",
        f"| Trustworthiness | {agg.get('trustworthiness', '?')} |",
        f"| **Overall** | **{agg.get('overall_score', '?')}** |",
        "",
    ]

    # ── Page-level E-E-A-T ──────────────────────────────────────────────────
    page_scores = eeat_scores.get("page_scores", {})
    critical_pages = [
        (url, s) for url, s in page_scores.items()
        if "parse_error" not in s and float(s.get("overall_score", 10)) < 6.0
    ]
    critical_pages.sort(key=lambda x: float(x[1].get("overall_score", 10)))

    if critical_pages:
        lines += [
            "## 🚨 Critical Pages (E-E-A-T < 6.0)",
            "",
            "These pages need immediate attention before competitor catch-up.",
            "",
        ]
        for url, scores in critical_pages[:8]:
            lines += [
                f"### `{url}`",
                f"- **Score:** {scores.get('overall_score')}/10",
                f"- **Top Issue:** {scores.get('top_issue', 'N/A')}",
                f"- **Quick Fix:** {scores.get('quick_fix', 'N/A')}",
                "",
            ]

    # ── Content Gap Analysis ────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "## 🕳️ Content Gap Analysis",
        "",
    ]

    gaps = gap_results.get("content_gaps", [])
    opps = gap_results.get("content_opportunities", [])
    strengths = gap_results.get("unique_strengths", [])

    if gaps:
        lines += ["### Topics Competitors Cover — You Don't", ""]
        for g in gaps[:15]:
            lines.append(f"- {g}")
        lines.append("")

    if opps:
        lines += ["### 🎯 Top 5 Content Opportunities", ""]
        for i, o in enumerate(opps[:5], 1):
            lines.append(f"{i}. {o}")
        lines.append("")

    if strengths:
        lines += ["### 💪 Your Unique Strengths (protect & amplify)", ""]
        for s in strengths[:8]:
            lines.append(f"- {s}")
        lines.append("")

    # ── Technical Issues ────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "## ⚙️ Technical SEO Issues",
        "",
        "| Issue | Count |",
        "|-------|-------|",
        f"| Missing meta descriptions | {tech_summary.get('missing_meta', 0)} |",
        f"| H1 issues (missing or multiple) | {tech_summary.get('h1_issues', 0)} |",
        f"| Images missing alt text | {tech_summary.get('alt_tag_issues', 0)} |",
        f"| Pages with no schema markup | {tech_summary.get('no_schema_pages', 0)} |",
        f"| Thin content pages (<300 words) | {tech_summary.get('thin_pages', 0)} |",
        f"| Missing canonical tags | {tech_summary.get('missing_canonical', 0)} |",
        "",
    ]

    # Schema opportunities
    schema_opps = technical.get("schema_opportunities", [])
    if schema_opps:
        lines += ["### 🏷️ Schema Opportunities (Ollama-assisted)", ""]
        for opp in schema_opps:
            lines += [
                f"- **`{opp.get('url', '')}`** → Add `{opp.get('priority_schema', '?')}` schema",
                f"  _{opp.get('reason', '')}_",
            ]
        lines.append("")

    # ── Next Steps ──────────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "## ✅ Recommended Next Steps",
        "",
        "**Immediate (Week 1):**",
        "1. Fix all missing meta descriptions",
        "2. Resolve H1 issues on every page",
        "3. Add alt text to all flagged images",
        "",
        "**Short-term (Month 1):**",
        "4. Add schema markup to top 10 priority pages",
        "5. Address E-E-A-T critical pages (score < 6.0) — author bios, trust signals, citations",
        "6. Assign top 3 content gaps to pillar page drafts",
        "",
        "**Growth (Month 2–3):**",
        "7. Build out content opportunities list as geo-programmatic pages",
        "8. Internal link audit to strengthen topical authority clusters",
        "9. Weekly freshness update cycle via n8n automation",
        "",
        "---",
        "",
        "> ⚠️ **Human Review Required** — All Ollama-generated scores and recommendations must be verified by the E-E-A-T Guardian before client delivery. Never auto-publish.",
        "",
        "*CapitalAI-Audit-Crawler — Ottawa's self-hosted AI SEO audit engine*",
    ]

    return lines
