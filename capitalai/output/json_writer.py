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
