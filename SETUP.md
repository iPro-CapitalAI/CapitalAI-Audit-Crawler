# CapitalAI-Audit-Crawler — Setup Guide

## What This Is
A CapitalAI upgrade layer built on top of the Crawl4AI fork.  
Crawl4AI provides: Playwright browser, JS rendering, markdown extraction, caching.  
Our layer adds: competitor mode, Ollama gap analysis, E-E-A-T scoring, agent JSON output.

---

## DELIVERABLE 1 — Step-by-Step Setup

### Phase A: On Your Phone (GitHub Web UI)

1. Go to `https://github.com/iPro-CapitalAI/CapitalAI-Audit-Crawler`
2. Click **"Add file" → "Upload files"**
3. Upload all files from the `capitalai/` folder you received
4. Commit message: `feat: add CapitalAI upgrade layer v1.0`

That's all for phone setup. Everything else runs on Windows.

---

### Phase B: Windows Machine (RTX 4090)

Open **PowerShell as Administrator** and run each block one at a time.

#### 1. Clone your fork
```powershell
cd C:\Projects
git clone https://github.com/iPro-CapitalAI/CapitalAI-Audit-Crawler.git
cd CapitalAI-Audit-Crawler
```

#### 2. Create Python 3.11 virtual environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### 3. Install Crawl4AI (the base library from the fork)
```powershell
pip install -e ".[all]"
crawl4ai-setup
```
> If `crawl4ai-setup` fails on Playwright, run: `playwright install chromium`

#### 4. Install CapitalAI additions
```powershell
pip install -r requirements-capitalai.txt
```

#### 5. Set up environment
```powershell
copy capitalai.env.example .env
# Edit .env if needed — defaults work for RTX 4090 + Ollama on localhost
```

#### 6. Verify Ollama is running with the right model
```powershell
ollama list
# If llama3.1:8b is not listed:
ollama pull llama3.1:8b
# Verify it responds:
ollama run llama3.1:8b "Say: Ollama is ready"
```

#### 7. Create reports folder
```powershell
mkdir reports
```

---

## DELIVERABLE 4 — Running Your First Test Crawl

### Quick test (client only, no Ollama — fastest sanity check)
```powershell
python capitalai/run_audit.py --client https://capitalai.ca --skip-eeat
```

### Full audit (client + E-E-A-T scoring)
```powershell
python capitalai/run_audit.py --client https://capitalai.ca
```

### Full audit with competitors
```powershell
python capitalai/run_audit.py `
  --client https://capitalai.ca `
  --competitors https://competitor1.ca `
  --competitors https://competitor2.ca `
  --competitors https://competitor3.ca
```

### Use a bigger model (if you have llama3.2 or better pulled)
```powershell
python capitalai/run_audit.py --client https://capitalai.ca --model llama3.2:latest
```

### Reports land in:
```
reports/
  capitalai_ca_20260326_1430_audit.md    ← Human review + client delivery
  capitalai_ca_20260326_1430_audit.json  ← 7-agent crew input
```

---

## DELIVERABLE 2 — Folder Structure

```
CapitalAI-Audit-Crawler/              ← Crawl4AI fork root (don't modify core)
│
├── crawl4ai/                         ← Crawl4AI core (upstream — do not edit)
├── docs/                             ← Crawl4AI docs
├── pyproject.toml                    ← Crawl4AI install config
│
├── capitalai/                        ← ALL CapitalAI code lives here ✅
│   ├── __init__.py
│   ├── run_audit.py                  ← CLI entry point
│   │
│   ├── config/
│   │   ├── settings.py               ← Ollama URL, crawl limits, scoring config
│   │   └── prompts.py                ← All Ollama prompt templates
│   │
│   ├── audit/
│   │   ├── competitor.py             ← Multi-site crawl via Crawl4AI
│   │   ├── gap_analysis.py           ← Ollama gap analysis + JSON parser
│   │   ├── eeat_scorer.py            ← Per-page + aggregate E-E-A-T scoring
│   │   └── technical.py              ← Schema, meta, H1, alt-tag checks
│   │
│   └── output/
│       ├── markdown_writer.py        ← Human-readable audit report
│       └── json_writer.py            ← Structured JSON for 7-agent crew
│
├── reports/                          ← All audit outputs (gitignored)
├── requirements-capitalai.txt        ← CapitalAI additions only
├── capitalai.env.example             ← Copy to .env
└── SETUP.md                          ← This file
```

---

## Troubleshooting

**Ollama not responding:**
```powershell
ollama serve   # Start Ollama server if not running
```

**Playwright browser error:**
```powershell
playwright install chromium
```

**crawl4ai-setup fails:**
```powershell
# Try manual setup:
pip install playwright
playwright install chromium
```

**Module not found errors:**
Make sure you're running from the repo root with venv activated:
```powershell
cd C:\Projects\CapitalAI-Audit-Crawler
.\venv\Scripts\Activate.ps1
python capitalai/run_audit.py --help
```

---

## Philosophy Reminder
- Zero paid APIs. Everything runs on your RTX 4090 + Ollama.
- Crawl4AI handles: JS rendering, browser pool, caching, Playwright.
- CapitalAI layer handles: competitor mode, Ollama calls, E-E-A-T scoring.
- Human gate: Nothing ships to a client without sign-off.
