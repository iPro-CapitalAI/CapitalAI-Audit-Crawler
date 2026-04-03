"""
CapitalAI Audit Control Panel
==============================
Flask web app — runs on your 4090 Windows machine.
Access from anywhere via Tailscale IP: http://<tailscale-ip>:5000

Start:  python app.py
Access: http://<tailscale-ip>:5000  (find your IP: tailscale ip -4)

Dependencies (all already in your stack):
  pip install flask --break-system-packages
"""

import os
import sys
import json
import time
import sqlite3
import asyncio
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, quote_plus
from functools import wraps
from queue import Queue, Empty

from flask import (Flask, render_template_string, request, redirect,
                   url_for, session, Response, jsonify, send_file)

# ── Config ────────────────────────────────────────────────────────────────────
PASSWORD      = "capitalai2026"          # change this anytime
SECRET_KEY    = "cap-ai-secret-2026"     # Flask session key
REPORTS_DIR   = Path(__file__).parent / "capitalai" / "output" / "reports"
RUN_AUDIT_PY  = Path(__file__).parent / "capitalai" / "run_audit.py"
DB_PATH       = Path(__file__).parent / "capitalai_audits.db"
PORT          = 5000
HOST          = "0.0.0.0"               # bind to all interfaces (Tailscale needs this)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            domain      TEXT,
            business    TEXT,
            location    TEXT,
            eeat_score  REAL,
            gaps        INTEGER,
            citation    TEXT,
            status      TEXT DEFAULT 'Lead',
            html_path   TEXT,
            pdf_path    TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes       TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_audit(domain, business, location, html_path, pdf_path,
               eeat_score=None, gaps=None, citation=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO audits (domain, business, location, eeat_score, gaps,
                            citation, html_path, pdf_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (domain, business, location, eeat_score, gaps, citation,
          str(html_path), str(pdf_path)))
    conn.commit()
    conn.close()

def get_recent_audits(limit=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM audits ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_audit_status(audit_id, status, notes=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE audits SET status=?, notes=? WHERE id=?",
                 (status, notes, audit_id))
    conn.commit()
    conn.close()

# ── Auth ──────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── Competitor discovery (Google Autocomplete — real data, no hallucinations) ─
async def _discover_competitors(client_url: str, location: str = "Ottawa") -> list[str]:
    """Scrape Google autocomplete for real competitor suggestions."""
    try:
        from playwright.async_api import async_playwright
        domain   = urlparse(client_url).netloc.replace("www.", "")
        category = _infer_category(domain)
        queries  = [
            f"{category} {location}",
            f"best {category} {location}",
            f"{category} near {location}",
        ]
        suggestions = set()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/122.0 Safari/537.36")
            for q in queries[:2]:  # limit to 2 queries
                url = f"https://www.google.ca/search?q={quote_plus(q)}"
                await page.goto(url, timeout=10000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                # Extract organic result URLs
                links = await page.eval_on_selector_all(
                    "cite", "els => els.map(e => e.textContent)")
                for link in links[:8]:
                    link = link.strip().split(" ")[0]
                    if link.startswith("http") or "." in link:
                        parsed = urlparse(link if "://" in link else "https://" + link)
                        netloc = parsed.netloc or parsed.path.split("/")[0]
                        netloc = netloc.replace("www.", "")
                        if netloc and netloc != domain and "google" not in netloc:
                            suggestions.add("https://www." + netloc)
            await browser.close()
        return list(suggestions)[:5]
    except Exception as e:
        return []

def _infer_category(domain: str) -> str:
    d = domain.lower()
    for kw, cat in [("dance","dance school"),("dental","dental clinic"),
                    ("law","law firm"),("consult","consulting firm"),
                    ("plumb","plumber"),("physio","physiotherapy"),
                    ("yoga","yoga studio"),("gym","gym"),
                    ("realty","real estate agent"),("seo","SEO agency"),
                    ("marketing","marketing agency"),("restaurant","restaurant")]:
        if kw in d: return cat
    return "local business"

# ── Live log streaming ────────────────────────────────────────────────────────
# Each audit run gets a queue. SSE endpoint drains it.
_audit_queues: dict[str, Queue] = {}
_audit_results: dict[str, dict] = {}

def _run_audit_subprocess(run_id: str, cmd: list[str]):
    """Run audit in thread, stream output to queue."""
    q = _audit_queues[run_id]
    q.put({"type": "start", "msg": f"Starting audit... ({' '.join(cmd)})"})
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(Path(__file__).parent),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                q.put({"type": "log", "msg": line})
        proc.wait()
        if proc.returncode == 0:
            # Find latest reports
            html_path = _find_latest_report("html")
            pdf_path  = _find_latest_report("pdf")
            _audit_results[run_id] = {
                "success": True,
                "html": str(html_path) if html_path else None,
                "pdf":  str(pdf_path)  if pdf_path  else None,
            }
            q.put({"type": "done", "html": str(html_path), "pdf": str(pdf_path)})
        else:
            q.put({"type": "error", "msg": f"Audit exited with code {proc.returncode}"})
    except Exception as e:
        q.put({"type": "error", "msg": str(e)})

def _find_latest_report(ext: str) -> Path | None:
    reports = list(REPORTS_DIR.glob(f"*.{ext}"))
    if not reports:
        return None
    return max(reports, key=lambda p: p.stat().st_mtime)

# ── HTML template ─────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capital AI — Login</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0d0d0d;font-family:'DM Sans',sans-serif;}
  .card{background:#141414;border:1px solid #222;border-radius:16px;padding:48px 40px;
        width:100%;max-width:380px;text-align:center;}
  .logo{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:#fff;
        letter-spacing:-.03em;margin-bottom:8px;}
  .logo span{color:#C0392B;}
  .sub{font-size:13px;color:#666;margin-bottom:32px;}
  input{width:100%;background:#0d0d0d;border:1px solid #333;border-radius:8px;
        padding:13px 16px;font-size:14px;color:#fff;font-family:'DM Sans',sans-serif;
        outline:none;transition:border .2s;}
  input:focus{border-color:#C0392B;}
  button{width:100%;margin-top:14px;background:#C0392B;color:#fff;border:none;
         border-radius:8px;padding:13px;font-size:14px;font-weight:500;
         font-family:'DM Sans',sans-serif;cursor:pointer;transition:background .2s;}
  button:hover{background:#96281b;}
  .err{color:#e74c3c;font-size:13px;margin-top:12px;}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Capital<span>AI</span>.ca</div>
  <div class="sub">Audit Control Panel</div>
  <form method="POST">
    <input type="password" name="password" placeholder="Enter password" autofocus>
    <button type="submit">Access Panel</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
  </form>
</div>
</body>
</html>"""

MAIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capital AI — Audit Panel</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#0d0d0d;--bg2:#111;--bg3:#141414;--border:#1e1e1e;--border2:#2a2a2a;
    --red:#C0392B;--red-dark:#96281B;--text:#f0ece4;--text2:#888;--text3:#555;
    --green:#16a34a;--amber:#d97706;
  }
  body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;
       font-size:14px;line-height:1.6;min-height:100vh;}

  /* Layout */
  .shell{display:grid;grid-template-columns:280px 1fr;min-height:100vh;max-width:1400px;margin:0 auto;}
  @media(max-width:768px){.shell{grid-template-columns:1fr;} .sidebar{display:none;}}

  /* Top bar */
  .topbar{background:var(--bg2);border-bottom:1px solid var(--border);
          padding:0 28px;height:56px;display:flex;align-items:center;
          justify-content:space-between;position:sticky;top:0;z-index:10;
          grid-column:1/-1;}
  .topbar-logo{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;
               color:var(--text);letter-spacing:-.03em;}
  .topbar-logo span{color:var(--red);}
  .topbar-right{display:flex;align-items:center;gap:16px;}
  .topbar-sub{font-size:12px;color:var(--text3);}
  .logout{font-size:12px;color:var(--text3);text-decoration:none;
          padding:5px 10px;border:1px solid var(--border2);border-radius:6px;
          transition:color .2s;}
  .logout:hover{color:var(--text2);}

  /* Sidebar */
  .sidebar{background:var(--bg2);border-right:1px solid var(--border);
           padding:24px 0;overflow-y:auto;}
  .sidebar-title{font-size:10px;font-weight:600;color:var(--text3);
                 text-transform:uppercase;letter-spacing:.1em;
                 padding:0 20px;margin-bottom:12px;}
  .audit-item{padding:12px 20px;border-bottom:1px solid var(--border);
              cursor:pointer;transition:background .15s;}
  .audit-item:hover{background:rgba(255,255,255,.03);}
  .audit-domain{font-size:13px;font-weight:500;color:var(--text);
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .audit-meta{font-size:11px;color:var(--text3);margin-top:3px;
              display:flex;gap:8px;align-items:center;}
  .score-badge{padding:2px 7px;border-radius:100px;font-size:10px;font-weight:600;}
  .score-weak{background:rgba(192,57,43,.15);color:#e74c3c;}
  .score-ok{background:rgba(214,151,23,.15);color:#d97706;}
  .score-strong{background:rgba(22,163,74,.15);color:#16a34a;}
  .status-badge{padding:2px 7px;border-radius:100px;font-size:10px;font-weight:500;
                border:1px solid var(--border2);color:var(--text3);}
  .audit-links{display:flex;gap:6px;margin-top:6px;}
  .audit-link{font-size:10px;color:var(--red);text-decoration:none;
              padding:2px 6px;border:1px solid rgba(192,57,43,.3);
              border-radius:4px;transition:background .15s;}
  .audit-link:hover{background:rgba(192,57,43,.1);}
  .empty-sidebar{padding:20px;font-size:12px;color:var(--text3);text-align:center;}

  /* Main */
  .main{padding:28px;display:flex;flex-direction:column;gap:20px;}

  /* Cards */
  .card{background:var(--bg3);border:1px solid var(--border);border-radius:12px;
        overflow:hidden;}
  .card-header{padding:14px 20px;border-bottom:1px solid var(--border);
               display:flex;align-items:center;gap:10px;}
  .card-icon{width:28px;height:28px;display:flex;align-items:center;justify-content:center;}
  .card-title{font-size:14px;font-weight:600;color:var(--text);}
  .card-body{padding:20px;}

  /* Form elements */
  label{display:block;font-size:11px;font-weight:500;color:var(--text3);
        text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;}
  input[type=text],input[type=url],textarea,select{
    width:100%;background:var(--bg2);border:1px solid var(--border2);
    border-radius:8px;padding:11px 14px;font-size:14px;color:var(--text);
    font-family:'DM Sans',sans-serif;outline:none;transition:border .2s;
    -webkit-appearance:none;}
  input:focus,textarea:focus{border-color:rgba(192,57,43,.6);}
  input::placeholder,textarea::placeholder{color:var(--text3);}
  textarea{resize:vertical;min-height:90px;}
  .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
  @media(max-width:600px){.form-grid{grid-template-columns:1fr;}}
  .form-field{margin-bottom:16px;}
  .form-hint{font-size:11px;color:var(--text3);margin-top:5px;}

  /* Competitor discovery */
  .discover-row{display:flex;gap:8px;align-items:flex-end;}
  .discover-row input{flex:1;}
  .btn-discover{background:var(--bg2);border:1px solid var(--border2);
                color:var(--text2);padding:11px 14px;border-radius:8px;
                font-size:13px;cursor:pointer;white-space:nowrap;
                transition:border .2s,color .2s;font-family:'DM Sans',sans-serif;}
  .btn-discover:hover{border-color:var(--red);color:var(--text);}
  .btn-discover.loading{opacity:.6;pointer-events:none;}

  /* Checkboxes */
  .checks{display:flex;gap:20px;flex-wrap:wrap;}
  .check-label{display:flex;align-items:center;gap:8px;font-size:13px;
               color:var(--text2);cursor:pointer;}
  .check-label input[type=checkbox]{width:16px;height:16px;accent-color:var(--red);}

  /* Buttons */
  .btn-primary{width:100%;background:var(--red);color:#fff;border:none;
               border-radius:10px;padding:15px;font-size:15px;font-weight:600;
               font-family:'DM Sans',sans-serif;cursor:pointer;
               transition:background .2s,transform .15s;letter-spacing:-.01em;}
  .btn-primary:hover{background:var(--red-dark);transform:translateY(-1px);}
  .btn-primary:disabled{opacity:.5;pointer-events:none;}

  /* Log stream */
  .log-box{background:#000;border:1px solid var(--border);border-radius:8px;
           padding:16px;height:320px;overflow-y:auto;font-family:'Courier New',monospace;
           font-size:12px;line-height:1.7;display:none;}
  .log-box.active{display:block;}
  .log-line{color:#ccc;}
  .log-line.success{color:#4ade80;}
  .log-line.error{color:#f87171;}
  .log-line.info{color:#60a5fa;}
  .log-line.warn{color:#fbbf24;}

  /* Result */
  .result-box{background:rgba(22,163,74,.08);border:1px solid rgba(22,163,74,.25);
              border-radius:10px;padding:20px;display:none;text-align:center;}
  .result-box.active{display:block;}
  .result-title{font-family:'Syne',sans-serif;font-size:20px;font-weight:700;
                color:#4ade80;margin-bottom:8px;}
  .result-sub{font-size:13px;color:var(--text3);margin-bottom:16px;}
  .result-links{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;}
  .result-link{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;
               border-radius:8px;font-size:14px;font-weight:500;text-decoration:none;
               transition:opacity .2s;}
  .result-link:hover{opacity:.85;}
  .rl-pdf{background:var(--red);color:#fff;}
  .rl-html{background:var(--bg2);border:1px solid var(--border2);color:var(--text);}

  /* Spinner */
  .spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.2);
           border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* Status selector */
  .status-select{background:var(--bg2);border:1px solid var(--border2);color:var(--text2);
                 border-radius:6px;padding:4px 8px;font-size:12px;cursor:pointer;}

  /* Pipeline overview */
  .pipeline{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
            background:var(--border);border-radius:8px;overflow:hidden;margin-bottom:4px;}
  @media(max-width:600px){.pipeline{grid-template-columns:repeat(2,1fr);}}
  .pipe-col{background:var(--bg3);padding:12px;text-align:center;}
  .pipe-num{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:var(--red);}
  .pipe-label{font-size:10px;color:var(--text3);text-transform:uppercase;
              letter-spacing:.06em;margin-top:2px;}
</style>
</head>
<body>

<div style="grid-column:1/-1;" class="topbar">
  <div class="topbar-logo">Capital<span>AI</span>.ca</div>
  <div class="topbar-right">
    <span class="topbar-sub">Audit Control Panel</span>
    <a href="/logout" class="logout">Sign out</a>
  </div>
</div>

<div class="shell" style="margin-top:56px;">

  <!-- Sidebar: Recent Audits -->
  <aside class="sidebar">
    <div class="sidebar-title">Recent Audits</div>
    {% if audits %}
      {% for a in audits %}
      <div class="audit-item">
        <div class="audit-domain">{{ a.domain }}</div>
        <div class="audit-meta">
          <span>{{ a.created_at[:10] }}</span>
          {% if a.eeat_score %}
            {% if a.eeat_score < 4 %}
              <span class="score-badge score-weak">{{ a.eeat_score }}/10</span>
            {% elif a.eeat_score < 6 %}
              <span class="score-badge score-ok">{{ a.eeat_score }}/10</span>
            {% else %}
              <span class="score-badge score-strong">{{ a.eeat_score }}/10</span>
            {% endif %}
          {% endif %}
          {% if a.citation %}
            <span style="font-size:10px;color:{% if a.citation == 'NOT CITED' %}#e74c3c{% else %}#16a34a{% endif %};">
              {{ a.citation }}
            </span>
          {% endif %}
        </div>
        <div class="audit-links">
          {% if a.html_path and a.html_path != 'None' %}
            <a href="/report/html/{{ a.id }}" target="_blank" class="audit-link">HTML</a>
          {% endif %}
          {% if a.pdf_path and a.pdf_path != 'None' %}
            <a href="/report/pdf/{{ a.id }}" target="_blank" class="audit-link">PDF</a>
          {% endif %}
          <select class="status-select" onchange="updateStatus({{ a.id }}, this.value)">
            {% for s in ['Lead','Sent Report','On Call','Proposal Sent','Retainer','Closed'] %}
              <option {% if a.status == s %}selected{% endif %}>{{ s }}</option>
            {% endfor %}
          </select>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty-sidebar">No audits yet.<br>Run your first one →</div>
    {% endif %}
  </aside>

  <!-- Main Panel -->
  <main class="main">

    <!-- Pipeline stats -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C0392B" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </div>
        <div class="card-title">Pipeline</div>
      </div>
      <div class="card-body" style="padding:16px 20px;">
        <div class="pipeline">
          <div class="pipe-col">
            <div class="pipe-num">{{ stats.leads }}</div>
            <div class="pipe-label">Leads</div>
          </div>
          <div class="pipe-col">
            <div class="pipe-num">{{ stats.sent }}</div>
            <div class="pipe-label">Reports Sent</div>
          </div>
          <div class="pipe-col">
            <div class="pipe-num">{{ stats.calls }}</div>
            <div class="pipe-label">On Call</div>
          </div>
          <div class="pipe-col">
            <div class="pipe-num">{{ stats.retainers }}</div>
            <div class="pipe-label">Retainers</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Audit Launcher -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C0392B" stroke-width="2"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 00-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 012-3.95A12.88 12.88 0 0122 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 01-4 2z"/></svg>
        </div>
        <div class="card-title">New Audit</div>
      </div>
      <div class="card-body">

        <div class="form-grid">
          <div class="form-field">
            <label>Client Website URL *</label>
            <input type="url" id="client-url" placeholder="https://yourbusiness.com" required>
          </div>
          <div class="form-field">
            <label>Business Name</label>
            <input type="text" id="business-name" placeholder="Leeming Dance Works">
            <div class="form-hint">Auto-inferred from URL if blank</div>
          </div>
        </div>

        <div class="form-grid">
          <div class="form-field">
            <label>Location</label>
            <input type="text" id="location" placeholder="Ottawa" value="Ottawa">
          </div>
          <div class="form-field" style="display:flex;flex-direction:column;justify-content:flex-end;">
            <div class="checks">
              <label class="check-label">
                <input type="checkbox" id="skip-grok" checked> Skip Grok
              </label>
              <label class="check-label">
                <input type="checkbox" id="skip-eeat"> Skip E-E-A-T
              </label>
              <label class="check-label">
                <input type="checkbox" id="skip-citations"> Skip Citations
              </label>
            </div>
          </div>
        </div>

        <div class="form-field">
          <label>Competitor URLs</label>
          <div class="discover-row">
            <textarea id="competitors" placeholder="https://competitor1.com&#10;https://competitor2.com" rows="3"></textarea>
          </div>
          <div style="margin-top:8px;display:flex;gap:8px;">
            <button class="btn-discover" id="discover-btn" onclick="discoverCompetitors()">
              🔍 Discover competitors
            </button>
            <span style="font-size:11px;color:var(--text3);align-self:center;">
              Scrapes Google — real results, not guesses
            </span>
          </div>
        </div>

        <!-- Log stream -->
        <div class="log-box" id="log-box"></div>

        <!-- Result -->
        <div class="result-box" id="result-box">
          <div class="result-title">Audit Complete ✓</div>
          <div class="result-sub" id="result-sub">Reports are ready</div>
          <div class="result-links" id="result-links"></div>
        </div>

        <button class="btn-primary" id="run-btn" onclick="runAudit()">
          🚀 Run Full Audit
        </button>

      </div>
    </div>

  </main>
</div>

<script>
// ── Competitor discovery ──────────────────────────────────────────────────────
async function discoverCompetitors() {
  const url = document.getElementById('client-url').value.trim();
  const loc = document.getElementById('location').value.trim() || 'Ottawa';
  if (!url) { alert('Enter the client URL first.'); return; }

  const btn = document.getElementById('discover-btn');
  btn.textContent = '⏳ Discovering...';
  btn.classList.add('loading');

  try {
    const res = await fetch('/discover', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url, location: loc})
    });
    const data = await res.json();
    if (data.competitors && data.competitors.length > 0) {
      document.getElementById('competitors').value = data.competitors.join('\\n');
      btn.textContent = `✓ Found ${data.competitors.length} competitors`;
    } else {
      btn.textContent = '⚠ None found — enter manually';
    }
  } catch(e) {
    btn.textContent = '✗ Error — enter manually';
  }
  btn.classList.remove('loading');
}

// ── Run audit ─────────────────────────────────────────────────────────────────
let currentRunId = null;
let eventSource  = null;

async function runAudit() {
  const clientUrl   = document.getElementById('client-url').value.trim();
  const business    = document.getElementById('business-name').value.trim();
  const location    = document.getElementById('location').value.trim() || 'Ottawa';
  const skipGrok    = document.getElementById('skip-grok').checked;
  const skipEeat    = document.getElementById('skip-eeat').checked;
  const skipCit     = document.getElementById('skip-citations').checked;
  const compRaw     = document.getElementById('competitors').value.trim();
  const competitors = compRaw ? compRaw.split('\\n').map(s=>s.trim()).filter(Boolean) : [];

  if (!clientUrl) { alert('Client URL is required.'); return; }

  // Reset UI
  const logBox    = document.getElementById('log-box');
  const resultBox = document.getElementById('result-box');
  const runBtn    = document.getElementById('run-btn');
  logBox.innerHTML = '';
  logBox.classList.add('active');
  resultBox.classList.remove('active');
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="spinner"></span> Running audit...';

  // Start audit
  const res = await fetch('/run', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({clientUrl, business, location, competitors,
                          skipGrok, skipEeat, skipCitations: skipCit})
  });
  const data = await res.json();
  currentRunId = data.run_id;

  // Stream logs via SSE
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/stream/${currentRunId}`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') {
      appendLog(msg.msg);
    } else if (msg.type === 'start') {
      appendLog(msg.msg, 'info');
    } else if (msg.type === 'done') {
      appendLog('Audit complete!', 'success');
      showResult(msg.html, msg.pdf);
      runBtn.disabled = false;
      runBtn.innerHTML = '🚀 Run Full Audit';
      eventSource.close();
    } else if (msg.type === 'error') {
      appendLog('ERROR: ' + msg.msg, 'error');
      runBtn.disabled = false;
      runBtn.innerHTML = '🚀 Run Full Audit';
      eventSource.close();
    }
  };
}

function appendLog(text, cls='') {
  const box = document.getElementById('log-box');
  const line = document.createElement('div');
  line.className = 'log-line' + (cls ? ' ' + cls : '');

  // Colour-code by content
  if (!cls) {
    if (text.includes('✓') || text.includes('OK') || text.includes('Complete')) cls = 'success';
    else if (text.includes('ERROR') || text.includes('✗') || text.includes('failed')) cls = 'error';
    else if (text.includes('[') && text.includes('/')) cls = 'info';
    else if (text.includes('⚠') || text.includes('Warning')) cls = 'warn';
    line.className = 'log-line ' + cls;
  }

  line.textContent = text;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function showResult(htmlPath, pdfPath) {
  const box   = document.getElementById('result-box');
  const links = document.getElementById('result-links');
  box.classList.add('active');
  links.innerHTML = '';

  if (pdfPath && pdfPath !== 'None') {
    const fn = pdfPath.split('\\\\').pop().split('/').pop();
    links.innerHTML += `<a href="/serve/${encodeURIComponent(fn)}?type=pdf" target="_blank" class="result-link rl-pdf">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      Open PDF Report
    </a>`;
  }
  if (htmlPath && htmlPath !== 'None') {
    const fn = htmlPath.split('\\\\').pop().split('/').pop();
    links.innerHTML += `<a href="/serve/${encodeURIComponent(fn)}?type=html" target="_blank" class="result-link rl-html">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
      Open HTML Report
    </a>`;
  }
}

// ── Status update ─────────────────────────────────────────────────────────────
async function updateStatus(auditId, status) {
  await fetch('/status', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id: auditId, status})
  });
}
</script>
</body>
</html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Wrong password."
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    audits = get_recent_audits(10)

    # Pipeline stats
    all_audits = get_recent_audits(500)
    stats = {
        "leads":    sum(1 for a in all_audits if a["status"] == "Lead"),
        "sent":     sum(1 for a in all_audits if a["status"] == "Sent Report"),
        "calls":    sum(1 for a in all_audits if a["status"] == "On Call"),
        "retainers":sum(1 for a in all_audits if a["status"] == "Retainer"),
    }
    return render_template_string(MAIN_HTML, audits=audits, stats=stats)

@app.route("/discover", methods=["POST"])
@login_required
def discover():
    data     = request.get_json()
    url      = data.get("url", "")
    location = data.get("location", "Ottawa")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        competitors = loop.run_until_complete(
            _discover_competitors(url, location))
        loop.close()
    except Exception as e:
        competitors = []
    return jsonify({"competitors": competitors})

@app.route("/run", methods=["POST"])
@login_required
def run():
    data        = request.get_json()
    client_url  = data.get("clientUrl", "")
    business    = data.get("business", "")
    location    = data.get("location", "Ottawa")
    competitors = data.get("competitors", [])
    skip_grok   = data.get("skipGrok", True)
    skip_eeat   = data.get("skipEeat", False)
    skip_cit    = data.get("skipCitations", False)

    run_id = f"run_{int(time.time()*1000)}"
    _audit_queues[run_id] = Queue()

    cmd = [sys.executable, str(RUN_AUDIT_PY),
           "--client", client_url,
           "--location", location]
    if business:
        cmd += ["--business", business]
    for comp in competitors:
        if comp.strip():
            cmd += ["--competitors", comp.strip()]
    if skip_grok:
        cmd.append("--skip-grok")
    if skip_eeat:
        cmd.append("--skip-eeat")
    if skip_cit:
        cmd.append("--skip-citations")

    t = threading.Thread(target=_run_audit_subprocess, args=(run_id, cmd), daemon=True)
    t.start()

    return jsonify({"run_id": run_id})

@app.route("/stream/<run_id>")
@login_required
def stream(run_id):
    def generate():
        q = _audit_queues.get(run_id)
        if not q:
            yield f"data: {json.dumps({'type':'error','msg':'Run not found'})}\n\n"
            return
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "error"):
                    # Save to DB on completion
                    if msg.get("type") == "done":
                        domain = urlparse(
                            _audit_queues.get(run_id + "_url", {})
                        ).netloc or "unknown"
                        try:
                            save_audit(
                                domain=domain,
                                business="",
                                location="Ottawa",
                                html_path=msg.get("html", ""),
                                pdf_path=msg.get("pdf", ""),
                            )
                        except Exception:
                            pass
                    break
            except Empty:
                yield f"data: {json.dumps({'type':'log','msg':'...'})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})

@app.route("/serve/<filename>")
@login_required
def serve_report(filename):
    ftype = request.args.get("type", "html")
    path  = REPORTS_DIR / filename
    if not path.exists():
        return "Report not found", 404
    mime = "application/pdf" if ftype == "pdf" else "text/html"
    return send_file(str(path), mimetype=mime)

@app.route("/report/<ftype>/<int:audit_id>")
@login_required
def serve_db_report(ftype, audit_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audits WHERE id=?", (audit_id,)).fetchone()
    conn.close()
    if not row:
        return "Not found", 404
    path = Path(row["html_path"] if ftype == "html" else row["pdf_path"])
    if not path.exists():
        return "File not found on disk", 404
    mime = "text/html" if ftype == "html" else "application/pdf"
    return send_file(str(path), mimetype=mime)

@app.route("/status", methods=["POST"])
@login_required
def status():
    data = request.get_json()
    update_audit_status(data["id"], data["status"])
    return jsonify({"ok": True})

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    print(f"""
╔══════════════════════════════════════════════╗
║       Capital AI — Audit Control Panel       ║
╠══════════════════════════════════════════════╣
║  Local:      http://localhost:{PORT}           ║
║  Tailscale:  http://<tailscale-ip>:{PORT}      ║
║                                              ║
║  Find your Tailscale IP:  tailscale ip -4    ║
║  Password:   capitalai2026                   ║
╚══════════════════════════════════════════════╝
""")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)