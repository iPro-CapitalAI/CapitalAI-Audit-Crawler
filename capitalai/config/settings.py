# capitalai/config/settings.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# ── Crawl limits ──────────────────────────────────────────────────────────────
CLIENT_CRAWL_DEPTH      = int(os.getenv("CLIENT_CRAWL_DEPTH", 3))   # BFS depth 3 = ~50-150 pages
COMPETITOR_CRAWL_DEPTH  = int(os.getenv("COMPETITOR_CRAWL_DEPTH", 2))  # BFS depth 2 = ~20-60 pages
MAX_PAGES_CLIENT        = int(os.getenv("MAX_PAGES_CLIENT", 150))   # Hard cap for BFS
MAX_PAGES_COMPETITOR    = int(os.getenv("MAX_PAGES_COMPETITOR", 50))   # Per competitor BFS cap
MAX_COMPETITORS         = 5

# Crawl4AI AsyncWebCrawler settings passed through
CRAWL4AI_HEADLESS       = True
CRAWL4AI_VERBOSE        = False
CRAWL4AI_WORD_COUNT_MIN = 100          # Skip near-empty pages

# ── E-E-A-T ───────────────────────────────────────────────────────────────────
MAX_PAGES_TO_SCORE = 12                # Ollama calls per audit (keep fast)

EEAT_PRIORITY_PATHS = [
    "/", "/about", "/about-us", "/services", "/service",
    "/contact", "/team", "/blog", "/pricing"
]

# ── Output ────────────────────────────────────────────────────────────────────
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")

# ── Bot identity (honest) ─────────────────────────────────────────────────────
USER_AGENT = "CapitalAI-Audit-Bot/1.0 (+https://capitalai.ca/bot)"
