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
                      else ("Meaningful gaps â€” add author bios and schema." if o >= 5.0
                            else "Immediate action required."))
    return avg
