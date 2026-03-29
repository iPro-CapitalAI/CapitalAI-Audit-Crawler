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
