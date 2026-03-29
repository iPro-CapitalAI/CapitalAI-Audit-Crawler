# capitalai/audit/gap_analysis.py
# Ollama-powered content gap analysis.
# Calls local llama3.1:8b — zero external APIs.

import json
import httpx
from rich.console import Console

from capitalai.config.settings import OLLAMA_BASE_URL, DEFAULT_MODEL
from capitalai.config.prompts import GAP_ANALYSIS_PROMPT
from capitalai.audit.competitor import extract_topics, extract_competitor_topics

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_gap_analysis(client_data: dict, competitor_data: dict, model: str = DEFAULT_MODEL) -> dict:
    """
    Build topic lists from crawl data, then ask Ollama to identify gaps.
    Returns structured dict with content_gaps, unique_strengths, content_opportunities.
    """
    client_topics = extract_topics(client_data)
    competitor_topics = extract_competitor_topics(competitor_data)

    if not competitor_topics:
        console.print("  [yellow]⚠ No competitor data — returning client topics as strengths.[/yellow]")
        return {
            "content_gaps": [],
            "unique_strengths": client_topics[:15],
            "content_opportunities": [],
            "note": "No competitor data provided."
        }

    # Cap list sizes to stay within Ollama context window
    client_sample   = "\n".join(f"- {t}" for t in client_topics[:80])
    comp_sample     = "\n".join(f"- {t}" for t in competitor_topics[:120])

    prompt = GAP_ANALYSIS_PROMPT.format(
        client_topics=client_sample,
        competitor_topics=comp_sample,
        competitor_count=len(competitor_data),
    )

    console.print(f"  [cyan]Ollama ({model}): running gap analysis...[/cyan]")
    raw = _call_ollama(prompt, model)
    return _parse_json_response(raw, fallback_key="raw_response")


# ─────────────────────────────────────────────────────────────────────────────
# Shared Ollama client (used by all audit modules)
# ─────────────────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> str:
    """
    POST to local Ollama /api/generate endpoint.
    Returns raw response string.
    Timeout: 120s — sufficient for llama3.1:8b on RTX 4090.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.15,
            "num_predict": max_tokens,
        },
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")
    except httpx.ConnectError:
        console.print("[red bold]✗ Ollama not running — start with: ollama serve[/red bold]")
        return ""
    except Exception as e:
        console.print(f"[red]✗ Ollama error: {e}[/red]")
        return ""


def _parse_json_response(raw: str, fallback_key: str = "raw") -> dict:
    """Strip markdown fences and parse JSON. Return fallback dict on failure."""
    if not raw:
        return {fallback_key: "", "parse_error": True}
    cleaned = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        console.print("  [yellow]⚠ JSON parse failed — returning raw.[/yellow]")
        return {fallback_key: raw, "parse_error": True}


# Export helper for other modules
call_ollama = _call_ollama
parse_json_response = _parse_json_response
