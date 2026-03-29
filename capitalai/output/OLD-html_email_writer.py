# capitalai/output/html_email_writer.py
# File: capitalai/output/html_email_writer.py
#
# FIXES IN THIS VERSION:
#   1. Sidebar: near-black #1A1F2E / #242B3D (Sitemate exact match, not navy)
#   2. Excerpt cleaner: strips [markdown](links), nav boilerplate, Skip to content
#   3. Red used sparingly: only score numbers and HIGH badges. Everything else is neutral.
#   4. Layout: sidebar uses position sticky + min-height 100vh fix for long pages
#   5. Pages Needing Attention: clean card, URL + score + issue + fix — no raw text

from datetime import datetime
from pathlib import Path
import re as _re

# ── Palette — Sitemate exact ──────────────────────────────────────────────────
SIDEBAR      = "#1C2333"     # exact Sitemate sidebar bg
SIDEBAR2     = "#253047"     # hover surface
SIDEBAR_ACT  = "#1E6CF0"     # exact Sitemate active blue
CONTENT_BG   = "#F3F4F6"     # very light gray page bg
TOPBAR       = "#FFFFFF"
CARD         = "#FFFFFF"
BORDER       = "#E5E7EB"
BORDER2      = "#D1D5DB"
PRIMARY      = "#3B82F6"     # blue
PRIMARY_L    = "#EFF6FF"
GREEN        = "#16A34A"
GREEN_L      = "#F0FDF4"
AMBER        = "#D97706"
AMBER_L      = "#FFFBEB"
RED          = "#DC2626"
RED_L        = "#FEF2F2"
INK          = "#111827"     # near-black text
INK2         = "#374151"     # secondary text
MUTED        = "#6B7280"
DIM          = "#9CA3AF"
SIDEBAR_TXT  = "#8FA3B8"     # exact inactive item text
SIDEBAR_MUT  = "#5A6A7E"     # section labels ADMIN/MANAGEMENT
BRAND_RED    = "#C0392B"     # CapitalAI logo only

F  = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
FM = "'JetBrains Mono','Fira Mono','Courier New',monospace"


# ── Excerpt cleaner ───────────────────────────────────────────────────────────

def _clean_excerpt(raw: str, max_words: int = 40) -> str:
    """
    Strip Crawl4AI markdown artifacts from body_excerpt before display.
    Removes: [Skip to content](url), [![](img)](url), markdown links,
    navigation boilerplate, Menu * items, bullet lists.
    Returns clean prose or empty string.
    """
    if not raw:
        return ""
    t = raw

    # Strip markdown image links [![](...))(...)
    t = _re.sub(r'!\[.*?\]\(.*?\)', '', t)
    # Strip markdown links [text](url) → text
    t = _re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)
    # Strip bare URLs
    t = _re.sub(r'https?://\S+', '', t)
    # Strip navigation boilerplate markers
    boilerplate = [
        "Skip to content", "Skip to main content",
        "Menu", "* Platforms", "* Systems", "* Pricing",
        "* Resources", "* Customers", "* Login", "* Watch demo",
        "Try for free", "Watch demo", "Log in", "Sign up",
    ]
    for phrase in boilerplate:
        t = t.replace(phrase, " ")
    # Strip bullet list markers
    t = _re.sub(r'\s*\*\s+', ' ', t)
    t = _re.sub(r'\s*[-–]\s+', ' ', t)
    # Strip leftover brackets and parens
    t = _re.sub(r'[\[\]()#]', ' ', t)
    # Collapse whitespace
    t = _re.sub(r'\s+', ' ', t).strip()

    # Take only the first meaningful sentence-like chunk
    # Split on sentence boundaries, pick first 2 real sentences
    sentences = _re.split(r'(?<=[.!?])\s+', t)
    good = []
    for s in sentences:
        s = s.strip()
        if len(s.split()) >= 5:   # skip fragments < 5 words
            good.append(s)
        if len(good) >= 2:
            break

    if good:
        result = " ".join(good)
    else:
        # Fallback: just first N words
        words = t.split()
        result = " ".join(words[:max_words])

    # Final word cap
    words = result.split()
    if len(words) > max_words:
        result = " ".join(words[:max_words]) + "…"

    return result.strip()


def _get_excerpt(page: dict, max_w: int = 40) -> str:
    raw = page.get("body_excerpt", "") or ""
    return _clean_excerpt(raw, max_w)


# ── Score helpers ─────────────────────────────────────────────────────────────

def _sc(score):
    try:
        s = float(score)
        return GREEN if s >= 7.5 else (AMBER if s >= 5.0 else RED)
    except (TypeError, ValueError):
        return DIM


def _sc_l(score):
    try:
        s = float(score)
        return GREEN_L if s >= 7.5 else (AMBER_L if s >= 5.0 else RED_L)
    except (TypeError, ValueError):
        return CONTENT_BG


def _bar(score, out_of=10, width=140):
    try:
        s = min(float(score), out_of)
    except (TypeError, ValueError):
        s = 0.0
    colour = _sc(s)
    fw = max(int(width * s / out_of), 0)
    ew = width - fw
    lbl = f"{s:.1f}/{out_of}"
    fc = (f'<td style="width:{fw}px;height:8px;background:{colour};'
          f'border-radius:4px 0 0 4px;" bgcolor="{colour}">&nbsp;</td>') if fw else ""
    ec = (f'<td style="width:{ew}px;height:8px;background:{BORDER};"'
          f' bgcolor="{BORDER}">&nbsp;</td>') if ew else ""
    lc = (f'<td style="padding-left:10px;font-family:{FM};font-size:12px;'
          f'font-weight:600;color:{colour};white-space:nowrap;">{lbl}</td>')
    return (f'<table cellpadding="0" cellspacing="0" border="0" '
            f'style="display:inline-table;vertical-align:middle;">'
            f'<tr>{fc}{ec}{lc}</tr></table>')


def _badge(text, colour, bg):
    return (f'<span style="display:inline-block;padding:2px 9px;border-radius:100px;'
            f'font-size:11px;font-weight:600;color:{colour};background:{bg};'
            f'font-family:{F};">{text}</span>')


def _score_badge(score):
    try:
        s = float(score)
        if s >= 7.5: return _badge("Strong",   GREEN, GREEN_L)
        if s >= 5.0: return _badge("Moderate", AMBER, AMBER_L)
        return _badge("Weak", RED, RED_L)
    except (TypeError, ValueError):
        return _badge("N/A", DIM, CONTENT_BG)


def _sev_badge(count):
    try:
        n = int(count)
        if n == 0: return _badge("Clear",    GREEN, GREEN_L)
        if n <= 3: return _badge("Moderate", AMBER, AMBER_L)
        return _badge("High", RED, RED_L)
    except (TypeError, ValueError):
        return _badge("?", DIM, CONTENT_BG)


def _priority_badge(rank):
    """rank 1-5 = HIGH, 6-10 = MED, 11+ = LOW"""
    if rank <= 5:   return _badge("HIGH", RED,   RED_L)
    if rank <= 10:  return _badge("MED",  AMBER, AMBER_L)
    return _badge("LOW", MUTED, CONTENT_BG)


# ── Layout primitives ─────────────────────────────────────────────────────────

def _card(inner, header_icon="", header_title=""):
    header = ""
    if header_title:
        header = (f'<div style="padding:9px 16px;background:#F9FAFB;'
                  f'border-bottom:1px solid {BORDER};display:flex;'
                  f'align-items:center;gap:7px;">'
                  f'<span style="color:{MUTED};display:inline-flex;">'
                  f'{header_icon}</span>'
                  f'<span style="font-size:12px;font-weight:600;color:{INK2};'
                  f'font-family:{F};">{header_title}</span>'
                  f'</div>')
    return (f'<div style="background:{CARD};border:1px solid {BORDER};'
            f'border-radius:8px;overflow:hidden;margin-bottom:14px;">'
            f'{header}'
            f'<div style="padding:16px 18px;">{inner}</div>'
            f'</div>')


def _table(headers, rows, widths=None):
    col_html = ""
    if widths:
        col_html = "<colgroup>" + "".join(
            f'<col style="width:{w};">' for w in widths) + "</colgroup>"
    th = "".join(
        f'<th style="padding:9px 14px;text-align:left;font-size:11px;font-weight:600;'
        f'color:{MUTED};text-transform:uppercase;letter-spacing:.5px;'
        f'background:#F9FAFB;border-bottom:1px solid {BORDER};'
        f'font-family:{F};">{h}</th>'
        for h in headers
    )
    tr_html = ""
    for i, row in enumerate(rows):
        bg = CARD if i % 2 == 0 else "#F9FAFB"
        cells = "".join(
            f'<td style="padding:11px 14px;font-size:13px;color:{INK2};'
            f'border-bottom:1px solid {BORDER};line-height:1.5;'
            f'vertical-align:top;font-family:{F};">{c}</td>'
            for c in row
        )
        tr_html += f'<tr style="background:{bg};">{cells}</tr>'
    head = f"<thead><tr>{th}</tr></thead>" if headers else ""
    return (f'<table cellpadding="0" cellspacing="0" border="0" width="100%"'
            f' style="border-collapse:collapse;font-family:{F};">'
            f'{col_html}{head}<tbody>{tr_html}</tbody></table>')


def _check_row(text, detail, done=False, colour=BORDER2):
    icon_col = GREEN if done else colour
    return (
        f'<tr>'
        f'<td style="width:32px;padding:10px 6px 10px 0;vertical-align:top;'
        f'text-align:center;">'
        f'<span style="display:inline-block;width:18px;height:18px;'
        f'border:2px solid {icon_col};border-radius:3px;background:{CARD};'
        f'margin-top:2px;'
        + (f'background:{GREEN};' if done else '')
        + f'"></span></td>'
        f'<td style="padding:10px 0;border-bottom:1px solid {BORDER};'
        f'vertical-align:top;">'
        f'<div style="font-size:13px;font-weight:500;color:{INK};'
        f'margin-bottom:2px;font-family:{F};">{text}</div>'
        f'<div style="font-size:12px;color:{MUTED};line-height:1.5;'
        f'font-family:{F};">{detail}</div>'
        f'</td></tr>'
    )


# ── SVG Icons ─────────────────────────────────────────────────────────────────
I_GRID  = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>'
I_STAR  = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'
I_SRCH  = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>'
I_STACK = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>'
I_CHECK = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>'
I_INFO  = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>'
I_USERS = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>'
I_TREND = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>'


# ── CSS ───────────────────────────────────────────────────────────────────────

def _css():
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ height: 100%; }}
body {{
  font-family: {F};
  font-size: 14px;
  line-height: 1.6;
  color: {INK};
  background: {CONTENT_BG};
  -webkit-text-size-adjust: 100%;
  min-height: 100vh;
}}
a {{ color: {PRIMARY}; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
strong {{ color: {INK}; font-weight: 600; }}
code {{
  font-family: {FM};
  background: #F1F5F9;
  color: {PRIMARY};
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  border: 1px solid {BORDER};
  word-break: break-all;
}}

/* ── Shell: sidebar + main ── */
.shell {{
  display: flex;
  min-height: 100vh;
  max-width: 1280px;
  margin: 0 auto;
  box-shadow: 0 0 0 1px {BORDER};
}}

/* ── Sidebar ── */
.sidebar {{
  width: 210px;
  flex-shrink: 0;
  background: {SIDEBAR};
  /* Sticky sidebar that stretches full height */
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}}
.sb-logo {{
  padding: 16px 16px 12px;
  border-bottom: 1px solid rgba(255,255,255,.07);
}}
.sb-chip {{
  margin: 10px 12px 6px;
  padding: 8px 10px;
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.09);
  border-radius: 6px;
}}
.sb-label {{
  padding: 14px 16px 5px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: {SIDEBAR_MUT};
}}
.nav-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  font-size: 13px;
  color: {SIDEBAR_TXT};
  cursor: default;
  transition: background .1s;
  border-radius: 0;
  text-decoration: none;
}}
.nav-item svg {{ opacity: .6; flex-shrink: 0; }}
.nav-item.active {{
  background: {SIDEBAR_ACT};
  color: #fff;
  font-weight: 600;
  border-radius: 6px;
  margin: 2px 8px;
  padding: 7px 10px;
}}
.nav-item.active svg {{ opacity: 1; }}
.nav-item:not(.active):hover {{ background: rgba(255,255,255,.05); }}

/* ── Main area ── */
.main {{
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: {CONTENT_BG};
}}

/* ── Top bar ── */
.topbar {{
  background: {TOPBAR};
  border-bottom: 1px solid {BORDER};
  padding: 0 24px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 10;
}}
.bc {{
  font-size: 13px;
  color: {MUTED};
  display: flex;
  align-items: center;
  gap: 6px;
}}
.bc .active {{ color: {INK}; font-weight: 500; }}

/* ── Page content ── */
.pc {{ padding: 22px 24px; flex: 1; }}

/* ── Page section header ── */
.ph {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding-top: 8px;
}}
.ph-icon {{
  width: 26px; height: 26px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
}}
.ph h2 {{
  font-size: 17px;
  font-weight: 700;
  color: {INK};
  letter-spacing: -.2px;
}}

/* ── Stat row ── */
.stats {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}}
.stat {{
  background: {CARD};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 14px 16px;
}}
.stat-lbl {{
  font-size: 10px;
  font-weight: 600;
  color: {MUTED};
  text-transform: uppercase;
  letter-spacing: .6px;
  margin-bottom: 6px;
}}
.stat-val {{
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 4px;
}}
.stat-sub {{
  font-size: 11px;
  color: {DIM};
}}

/* ── 2-col grid ── */
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }}
.col-full {{ grid-column: 1 / -1; }}

/* ── Page attention card ── */
.pa-card {{
  background: {CARD};
  border: 1px solid {BORDER};
  border-left: 3px solid {BORDER2};
  border-radius: 0 8px 8px 0;
  padding: 14px 16px;
  margin-bottom: 10px;
}}

/* ── Opportunity card ── */
.opp-card {{
  border: 1px solid {BORDER};
  border-left: 3px solid {PRIMARY};
  border-radius: 0 8px 8px 0;
  padding: 14px 16px;
  margin-bottom: 10px;
  background: {CARD};
}}

/* ── Section separator ── */
.sep {{ height: 6px; }}

/* ── Gate banner ── */
.gate {{
  background: {AMBER_L};
  border: 1px solid #FCD34D;
  border-left: 3px solid {AMBER};
  border-radius: 6px;
  padding: 9px 14px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #92400E;
}}

/* ── Phase heading ── */
.phase {{
  font-size: 13px;
  font-weight: 700;
  padding: 8px 12px;
  border-radius: 6px;
  margin: 16px 0 8px;
}}

/* ── CTA ── */
.cta {{
  background: {SIDEBAR};
  padding: 28px 24px;
  text-align: center;
}}

/* ── Responsive ── */
@media (max-width: 960px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 768px) {{
  .sidebar {{ display: none; }}
  .grid2 {{ grid-template-columns: 1fr; }}
  .pc {{ padding: 16px; }}
  .topbar {{ padding: 0 16px; }}
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 480px) {{
  .stats {{ grid-template-columns: 1fr; }}
}}
</style>"""


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar(domain):
    """Sitemate-exact sidebar: dark bg, ADMIN/MANAGEMENT section groups, active blue pill."""
    short = domain[:22] + "…" if len(domain) > 24 else domain

    def _nav(icon, label, active=False):
        if active:
            return (f'<div class="nav-item active">'
                    f'<span style="display:inline-flex;align-items:center;width:16px;">{icon}</span>'
                    f'{label}</div>')
        return (f'<div class="nav-item">'
                f'<span style="display:inline-flex;align-items:center;width:16px;opacity:.55;">{icon}</span>'
                f'{label}</div>')

    def _slabel(text):
        return (f'<div style="padding:14px 16px 5px;font-size:10px;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:1.1px;color:{SIDEBAR_MUT};'
                f'font-family:{F};">{text}</div>')

    return (
        f'<div class="sidebar">'

        # Logo + workspace block
        f'<div style="padding:16px 16px 14px;border-bottom:1px solid rgba(255,255,255,.06);">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
        f'<div style="width:28px;height:28px;border-radius:6px;background:#E05A4B;'
        f'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">'
        f'<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>'
        f'<polyline points="9,22 9,12 15,12 15,22"/></svg></div>'
        f'<div>'
        f'<div style="font-size:14px;font-weight:700;color:#fff;letter-spacing:-.2px;font-family:{F};">'
        f'Capital<span style="color:#E05A4B;">AI</span></div>'
        f'<div style="font-size:10px;color:{SIDEBAR_MUT};font-family:{F};">SEO Audit Platform</div>'
        f'</div></div>'
        # Workspace chip — mirrors "ABC Contractors" from Sitemate
        f'<div style="display:flex;align-items:center;gap:7px;padding:7px 9px;'
        f'background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:5px;">'
        f'<div style="width:20px;height:20px;border-radius:4px;background:{SIDEBAR_ACT};'
        f'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">'
        f'<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>'
        f'<rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></div>'
        f'<span style="font-size:12px;font-weight:500;color:#D0DCE8;font-family:{F};">{short}</span>'
        f'</div></div>'

        # ADMIN section
        + _slabel("Admin")
        + _nav(I_GRID, "Executive Summary", active=True)
        + _nav(I_STAR, "E-E-A-T Scorecard")
        + _nav(I_SRCH, "Content Gaps")

        # ANALYSIS section
        + _slabel("Analysis")
        + _nav(I_STACK, "Technical Health")
        + _nav(I_CHECK, "Action Plan")
        + _nav(I_INFO,  "About")

        # Footer
        + f'<div style="margin-top:auto;padding:14px 16px;border-top:1px solid rgba(255,255,255,.05);">'
        f'<div style="font-size:10px;color:{SIDEBAR_MUT};line-height:1.6;">'
        f'Crawl4AI · Ollama llama3.1:8b<br>100% local · zero cloud</div>'
        f'</div>'
        f'</div>'
    )
def _topbar(domain, date_str):
    return (
        f'<div class="topbar">'
        f'<div class="bc">'
        f'<span>CapitalAI Audit</span>'
        f'<span>›</span>'
        f'<span class="active">{domain}</span>'
        f'<span>›</span>'
        f'<span class="active">Full Audit Report</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<span style="font-size:12px;color:{DIM};">{date_str}</span>'
        f'<span style="padding:2px 10px;border-radius:100px;background:{RED_L};'
        f'font-size:11px;font-weight:600;color:{RED};">Confidential</span>'
        f'</div>'
        f'</div>'
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _s_summary(domain, client_data, competitor_data, eeat_scores, technical):
    agg     = eeat_scores.get("site_aggregate", {})
    tech    = technical.get("summary", {})
    overall = agg.get("overall_score", "N/A")
    verdict = agg.get("verdict", "")
    n_pages = len(client_data)
    n_comps = len(competitor_data)
    issues  = (tech.get("missing_meta", 0)
               + tech.get("h1_issues", 0)
               + tech.get("no_schema_pages", 0))

    try:
        o = float(overall)
        htxt = "Strong" if o >= 7.5 else ("Needs Work" if o >= 5.0 else "Needs Attention")
        hcol = GREEN if o >= 7.5 else (AMBER if o >= 5.0 else RED)
    except (TypeError, ValueError):
        htxt, hcol = "Not Scored", DIM

    # Worst page callout
    page_scores = eeat_scores.get("page_scores", {})
    wu, ws, wsc = None, {}, 10.0
    for url, s in page_scores.items():
        if "parse_error" not in s:
            try:
                sc = float(s.get("overall_score", 10))
                if sc < wsc:
                    wsc, wu, ws = sc, url, s
            except (TypeError, ValueError):
                pass

    worst_inner = (
        f'<div style="background:{RED_L};border-left:3px solid {RED};'
        f'border-radius:0 6px 6px 0;padding:12px 14px;">'
        f'<code style="font-size:11px;display:block;margin-bottom:6px;">{wu}</code>'
        f'<div style="font-size:20px;font-weight:700;color:{RED};margin-bottom:6px;">'
        f'{wsc}/10</div>'
        f'<div style="font-size:13px;color:{INK2};margin-bottom:5px;">'
        f'{ws.get("top_issue","N/A")}</div>'
        f'<div style="font-size:12px;color:{GREEN};font-weight:500;">'
        f'Fix: {ws.get("quick_fix","N/A")}</div>'
        f'</div>'
    ) if wu else (f'<div style="text-align:center;padding:20px;color:{DIM};'
                  f'font-size:13px;">No critical pages found.</div>')

    health_rows = [
        [f'<span style="color:{INK2};">Overall Health</span>',
         _badge(htxt, hcol, _sc_l(overall))],
        [f'<span style="color:{INK2};">E-E-A-T Score</span>',
         f'<strong style="color:{_sc(overall)};">{overall}/10</strong>'],
        [f'<span style="color:{INK2};">Technical Issues</span>',
         f'<strong style="color:{"#DC2626" if issues > 0 else GREEN};">{issues} found</strong>'],
        [f'<span style="color:{INK2};">Competitors Analyzed</span>',
         f'<strong style="color:{PRIMARY};">{n_comps}</strong>'],
    ]

    verdict_block = (
        f'<div style="background:{PRIMARY_L};border-left:3px solid {PRIMARY};'
        f'border-radius:0 6px 6px 0;padding:10px 12px;margin-top:10px;">'
        f'<div style="font-size:10px;font-weight:700;color:{PRIMARY};'
        f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;">Bottom Line</div>'
        f'<div style="font-size:13px;color:{INK2};">{verdict}</div>'
        f'</div>'
    ) if verdict else ""

    return (
        f'<div class="ph">'
        f'<div class="ph-icon" style="background:{PRIMARY};">{I_GRID}</div>'
        f'<h2>Executive Summary</h2></div>'

        # 4-stat row
        f'<div class="stats">'
        f'<div class="stat" style="border-top:3px solid {PRIMARY};">'
        f'<div class="stat-lbl">Pages Audited</div>'
        f'<div class="stat-val" style="color:{PRIMARY};">{n_pages}</div>'
        f'</div>'
        f'<div class="stat" style="border-top:3px solid {_sc(overall)};">'
        f'<div class="stat-lbl">E-E-A-T Score</div>'
        f'<div class="stat-val" style="color:{_sc(overall)};">{overall}/10</div>'
        f'<div class="stat-sub">{htxt}</div>'
        f'</div>'
        f'<div class="stat" style="border-top:3px solid {"#DC2626" if issues > 0 else GREEN};">'
        f'<div class="stat-lbl">Technical Issues</div>'
        f'<div class="stat-val" style="color:{"#DC2626" if issues > 0 else GREEN};">'
        f'{issues}</div>'
        f'</div>'
        f'<div class="stat" style="border-top:3px solid {AMBER};">'
        f'<div class="stat-lbl">Competitors</div>'
        f'<div class="stat-val" style="color:{AMBER};">{n_comps}</div>'
        f'</div>'
        f'</div>'

        # 2-col: health table + critical finding
        + f'<div class="grid2">'
        + _card(_table([], health_rows, ["52%", "48%"]) + verdict_block,
                I_GRID, "Site Health Overview")
        + _card(worst_inner, I_STAR, "Most Critical Finding")
        + f'</div>'
    )


def _s_eeat(eeat_scores, client_data):
    agg         = eeat_scores.get("site_aggregate", {})
    page_scores = eeat_scores.get("page_scores", {})

    html = (f'<div class="ph">'
            f'<div class="ph-icon" style="background:#7C3AED;">{I_STAR}</div>'
            f'<h2>E-E-A-T Scorecard</h2></div>')

    if not agg or "error" in agg:
        return html + _card(
            f'<p style="color:{MUTED};font-size:13px;">Scoring skipped. '
            f'Re-run without <code>--skip-eeat</code>.</p>', I_STAR, "E-E-A-T")

    dims = [
        ("Experience",        agg.get("experience",        0), "First-hand signals"),
        ("Expertise",         agg.get("expertise",         0), "Subject-matter depth"),
        ("Authoritativeness", agg.get("authoritativeness", 0), "Author bios, citations"),
        ("Trustworthiness",   agg.get("trustworthiness",   0), "Contact, HTTPS, privacy"),
    ]
    overall = agg.get("overall_score", 0)

    rows = []
    for label, score, meaning in dims:
        rows.append([
            f'<span style="color:{INK2};font-weight:500;">{label}</span>',
            f'<strong style="font-size:14px;color:{_sc(score)};">{score}/10</strong>',
            _bar(score, width=120),
            f'<span style="font-size:12px;color:{MUTED};">{meaning}</span>',
        ])
    rows.append([
        f'<strong style="color:{INK};">Overall</strong>',
        f'<strong style="font-size:16px;color:{_sc(overall)};">{overall}/10</strong>',
        _bar(overall, width=120),
        _score_badge(overall),
    ])
    html += _card(_table(["Dimension", "Score", "Visual", "Signal"], rows,
                          ["24%", "13%", "35%", "28%"]),
                  I_STAR, "Site-Level E-E-A-T Score")

    # Pages needing attention — CLEAN version
    weak = [(u, s) for u, s in page_scores.items()
            if "parse_error" not in s
            and float(s.get("overall_score", 10) or 10) < 6.0]
    weak.sort(key=lambda x: float(x[1].get("overall_score", 10) or 10))

    if weak:
        html += (f'<div style="font-size:13px;font-weight:600;color:{INK};'
                 f'margin:16px 0 10px;">Pages Needing Attention</div>'
                 f'<div class="grid2">')
        for url, sc in weak[:6]:
            page    = client_data.get(url, {})
            score_v = sc.get("overall_score", "?")
            issue   = sc.get("top_issue",     "N/A")
            fix_v   = sc.get("quick_fix",     "N/A")
            wc      = page.get("word_count",  "?")
            col     = _sc(score_v)
            ex      = _get_excerpt(page, 35)   # ← cleaned excerpt

            # Clean URL display — just the path
            try:
                from urllib.parse import urlparse as _up
                path = _up(url).path.rstrip("/") or "/"
                display_url = path if len(path) < 45 else path[:42] + "…"
            except Exception:
                display_url = url[:45]

            excerpt_html = (
                f'<div style="padding:8px 10px;background:{PRIMARY_L};'
                f'border-radius:4px;margin-bottom:10px;">'
                f'<div style="font-size:10px;font-weight:600;color:{PRIMARY};'
                f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;">'
                f'Page Preview</div>'
                f'<div style="font-size:12px;color:{INK2};line-height:1.5;">{ex}</div>'
                f'</div>'
            ) if ex else ""
            html += (
                f'<div class="pa-card" style="border-left-color:{col};">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:6px;">'
                f'<code style="font-size:11px;color:{PRIMARY};">{display_url}</code>'
                f'<strong style="font-size:18px;color:{col};white-space:nowrap;">'
                f'{score_v}/10</strong>'
                f'</div>'
                f'<div style="margin-bottom:10px;">{_bar(score_v, width=160)}</div>'
                + excerpt_html +
                f'<div style="border-top:1px solid {BORDER};padding-top:8px;">'
                f'<div style="font-size:12px;margin-bottom:4px;color:{INK2};">'
                f'<span style="font-weight:600;color:{RED};">Issue</span>'
                f'<span style="color:{MUTED};"> · {wc} words</span></div>'
                f'<div style="font-size:12px;color:{INK2};margin-bottom:6px;">{issue}</div>'
                f'<div style="font-size:12px;color:{GREEN};font-weight:500;">'
                f'→ {fix_v}</div>'
                f'</div>'
                f'</div>'
            )
        html += '</div>'

    # Strong pages
    strong = [(u, s) for u, s in page_scores.items()
              if "parse_error" not in s
              and float(s.get("overall_score", 0) or 0) >= 6.0]
    if strong:
        srows = []
        for url, sc in strong[:5]:
            try:
                from urllib.parse import urlparse as _up
                path = _up(url).path.rstrip("/") or "/"
            except Exception:
                path = url
            srows.append([
                f'<code style="font-size:11px;color:{PRIMARY};">{path}</code>',
                f'<strong style="color:{GREEN};font-size:14px;">'
                f'{sc.get("overall_score","?")}/10</strong>',
                f'<span style="font-size:12px;color:{MUTED};">Use as internal link source</span>',
            ])
        html += (f'<div style="font-size:13px;font-weight:600;color:{INK};'
                 f'margin:16px 0 10px;">Strong Pages — Protect &amp; Amplify</div>'
                 + _card(_table(["Page", "Score", "Recommended Action"],
                                srows, ["45%", "15%", "40%"]),
                         I_STAR, "High E-E-A-T Pages"))

    return html


def _s_gaps(gap_results, competitor_data):
    gaps      = gap_results.get("content_gaps", [])
    opps      = gap_results.get("content_opportunities", [])
    strengths = gap_results.get("unique_strengths", [])

    html = (f'<div class="ph">'
            f'<div class="ph-icon" style="background:#0891B2;">{I_SRCH}</div>'
            f'<h2>Content Gap Analysis</h2></div>')

    if not competitor_data:
        return html + _card(
            f'<p style="color:{MUTED};font-size:13px;">No competitors crawled. '
            f'Re-run with <code>--competitors https://comp.ca</code>.</p>',
            I_SRCH, "Gap Analysis")

    total_pages = sum(len(v) for v in competitor_data.values()
                      if isinstance(v, dict))

    # Competitor snapshot + gap count
    comp_rows = [
        [f'<code style="font-size:11px;color:{PRIMARY};">{url}</code>',
         f'<strong style="color:{INK};">{len(pages)}</strong>']
        for url, pages in competitor_data.items() if isinstance(pages, dict)
    ]
    gap_stat = (
        f'<div style="text-align:center;padding:14px 0;">'
        f'<div style="font-size:44px;font-weight:700;'
        f'color:{"#DC2626" if gaps else GREEN};line-height:1;">{len(gaps)}</div>'
        f'<div style="font-size:12px;color:{MUTED};margin-top:4px;">topic gaps identified</div>'
        f'<div style="font-size:11px;color:{DIM};margin-top:6px;">'
        f'{total_pages} competitor pages analyzed</div>'
        f'</div>'
    )

    html += (f'<div class="grid2">'
             + _card(_table(["Competitor", "Pages"], comp_rows, ["74%", "26%"]),
                     I_USERS, "Competitor Snapshot")
             + _card(gap_stat, I_SRCH, "Gap Summary")
             + f'</div>')

    if gaps:
        gap_rows = []
        for i, g in enumerate(gaps[:15], 1):
            gap_rows.append([
                f'<span style="color:{MUTED};font-weight:500;">{i}</span>',
                f'<span style="color:{INK};">{g}</span>',
                _priority_badge(i),
            ])
        html += _card(_table(["#", "Missing Topic", "Priority"], gap_rows,
                              ["5%", "73%", "22%"]),
                      I_SRCH, "Topics Competitors Own — You Don't")

    if opps:
        html += (f'<div style="font-size:13px;font-weight:600;color:{INK};'
                 f'margin:16px 0 10px;">Top Content Opportunities</div>'
                 f'<div class="grid2">')
        for i, opp in enumerate(opps[:4], 1):
            html += (
                f'<div class="opp-card">'
                f'<div style="font-size:10px;font-weight:700;color:{PRIMARY};'
                f'text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;">'
                f'Opportunity {i}</div>'
                f'<div style="font-size:14px;font-weight:600;color:{INK};'
                f'margin-bottom:6px;line-height:1.4;">{opp.strip().rstrip(".")}</div>'
                f'<div style="font-size:11px;color:{MUTED};">'
                f'1,200+ words · Schema markup · Internal links</div>'
                f'</div>'
            )
        html += '</div>'

    if strengths:
        items = "".join(
            f'<li style="padding:8px 0;border-bottom:1px solid {BORDER};'
            f'font-size:13px;color:{INK2};list-style:none;">'
            f'<span style="color:{GREEN};margin-right:6px;font-weight:600;">✓</span>{s}</li>'
            for s in strengths[:8]
        )
        html += _card(f'<ul style="padding:0;margin:0;">{items}</ul>',
                      I_TREND, "Your Competitive Advantages")

    return html


def _s_technical(technical, client_data):
    tech = technical.get("summary", {})
    data = [
        ("Missing meta descriptions", tech.get("missing_meta",      0), "Hurts CTR — Google writes them poorly"),
        ("H1 tag issues",             tech.get("h1_issues",         0), "Confuses crawlers on topic"),
        ("Images missing alt text",   tech.get("alt_tag_issues",    0), "Accessibility + image search loss"),
        ("Pages without schema",      tech.get("no_schema_pages",   0), "Missing rich result eligibility"),
        ("Thin content (<300 words)", tech.get("thin_pages",        0), "E-E-A-T risk under Helpful Content"),
        ("Missing canonical tags",    tech.get("missing_canonical", 0), "Duplicate content signal"),
    ]
    total = sum(r[1] for r in data)

    html = (f'<div class="ph">'
            f'<div class="ph-icon" style="background:#059669;">{I_STACK}</div>'
            f'<h2>Technical SEO Health</h2></div>')

    rows = []
    for label, count, impact in data:
        # Count colour: red only if actually high, amber for moderate, green for zero
        cnt_col = GREEN if count == 0 else (RED if count > 3 else AMBER)
        rows.append([
            f'<span style="color:{INK2};font-weight:500;">{label}</span>',
            f'<strong style="font-size:16px;color:{cnt_col};">{count}</strong>',
            _sev_badge(count),
            f'<span style="font-size:12px;color:{MUTED};">{impact}</span>',
        ])

    html += _card(
        f'<div style="font-size:12px;color:{MUTED};margin-bottom:12px;">'
        f'Scanned <strong style="color:{INK};">'
        f'{tech.get("total_pages", len(client_data))} pages</strong> · '
        f'<strong style="color:{"#DC2626" if total > 0 else GREEN};">'
        f'{total} issues</strong> found</div>'
        + _table(["Issue", "Count", "Severity", "Impact"], rows,
                 ["32%", "10%", "16%", "42%"]),
        I_STACK, "Issue Summary"
    )

    schema_opps = technical.get("schema_opportunities", [])
    thin        = technical.get("thin_content", [])

    if schema_opps or thin:
        left_c = right_c = ""
        if schema_opps:
            orows = [[
                f'<code style="font-size:11px;color:{PRIMARY};">{o.get("url","")}</code>',
                f'<strong style="color:{GREEN};font-size:12px;">{o.get("priority_schema","?")}</strong>',
                f'<span style="font-size:11px;color:{MUTED};">{o.get("reason","")}</span>',
            ] for o in schema_opps]
            left_c = _card(_table(["Page", "Add Schema", "Why"], orows,
                                   ["38%", "22%", "40%"]),
                           I_STACK, "Schema Opportunities")
        if thin:
            trows = [[
                f'<code style="font-size:11px;color:{PRIMARY};">{i.get("url","")}</code>',
                f'<strong style="color:{AMBER};font-size:14px;">{i.get("word_count",0)}</strong>',
                f'<span style="font-size:11px;color:{MUTED};">'
                f'{"Expand to 800+" if i.get("word_count",0) > 100 else "Consolidate"}</span>',
            ] for i in thin[:8]]
            right_c = _card(_table(["Page", "Words", "Action"], trows,
                                    ["55%", "15%", "30%"]),
                            I_STACK, "Thin Content Pages")
        if left_c and right_c:
            html += f'<div class="grid2">{left_c}{right_c}</div>'
        elif left_c:
            html += left_c
        elif right_c:
            html += right_c

    return html


def _s_plan(eeat_scores, gap_results, technical):
    tech        = technical.get("summary", {})
    mm          = tech.get("missing_meta",    0)
    h1          = tech.get("h1_issues",       0)
    ns          = tech.get("no_schema_pages", 0)
    tp          = tech.get("thin_pages",      0)
    gaps        = gap_results.get("content_gaps", [])
    opps        = gap_results.get("content_opportunities", [])
    page_scores = eeat_scores.get("page_scores", {})
    crit        = sum(1 for s in page_scores.values()
                      if "parse_error" not in s
                      and float(s.get("overall_score", 10) or 10) < 5.0)

    html = (f'<div class="ph">'
            f'<div class="ph-icon" style="background:{AMBER};">{I_CHECK}</div>'
            f'<h2>Prioritized Action Plan</h2></div>')

    phases = [
        ("Week 1 — Fix the Foundation", RED, RED_L, "#FCA5A5", [
            (f"Write meta descriptions for {mm} page(s)" if mm else "✓ Meta descriptions complete",
             "Direct CTR impact — 30 min per page", RED if mm else GREEN, mm == 0),
            (f"Fix H1 tags on {h1} page(s)" if h1 else "✓ H1 tags healthy",
             "Critical for crawler topic understanding", RED if h1 else GREEN, h1 == 0),
            (f"E-E-A-T repair on {crit} critical page(s)" if crit else "✓ No critical E-E-A-T pages",
             "Add author bio, trust signals, citations", RED if crit else GREEN, crit == 0),
        ]),
        ("Month 1 — Build Authority", AMBER, AMBER_L, "#FCD34D", [
            (f"Add schema to {ns} unstructured page(s)", "Unlock rich result eligibility", AMBER, False),
            (f"Expand {tp} thin page(s) to 800+ words", "Reduce Helpful Content demotion risk", AMBER, False),
            ("Add author bio to all content pages", "Highest single-ROI E-E-A-T improvement", AMBER, False),
            ("Internal link audit — connect strong to weak", "Distribute E-E-A-T authority", AMBER, False),
        ]),
        ("Month 2–3 — Scale & Dominate", GREEN, GREEN_L, "#86EFAC", [
            (f"Create {min(len(opps),5)} pillar pages from opportunities",
             "Close identified traffic gaps", GREEN, False),
            (f"Close {len(gaps)} content gaps with targeted articles",
             "Each = writer brief + schema requirement", GREEN, False),
            ("Geo-programmatic expansion — Ottawa + NCR",
             "KrispCall/Flyhomes-style scale play", GREEN, False),
            ("Weekly freshness automation via n8n", "Maintain ranking momentum", GREEN, False),
            ("AI citation targeting — restructure as answer capsules",
             "Perplexity, ChatGPT, Claude citations", GREEN, False),
        ]),
    ]

    inner = f'<div style="font-size:12px;color:{MUTED};margin-bottom:14px;">Tasks ordered by ROI impact. Complete in sequence for maximum compounding effect.</div>'
    for phase_title, phase_col, phase_bg, phase_border, tasks in phases:
        inner += (f'<div class="phase" style="background:{phase_bg};'
                  f'color:{phase_col};border:1px solid {phase_border};">'
                  f'{phase_title}</div>'
                  f'<table cellpadding="0" cellspacing="0" border="0" '
                  f'width="100%" style="margin-bottom:4px;">')
        for task, detail, col, done in tasks:
            inner += _check_row(task, detail, done=done, colour=col)
        inner += "</table>"

    html += _card(inner, I_CHECK, "Tasks ordered by ROI impact")
    return html


def _s_about(domain, model):
    now = datetime.now().strftime("%B %d, %Y at %H:%M")
    rows_data = [
        ("Generated",  now),
        ("Domain",     domain),
        ("Engine",     "CapitalAI-Audit-Crawler v1.0"),
        ("Crawler",    "Crawl4AI — Playwright, full JS rendering"),
        ("AI Model",   f"Ollama {model} — 100% local inference"),
        ("Privacy",    "No client data left your machine. Zero cloud APIs."),
        ("Review",     "E-E-A-T Guardian sign-off required before delivery"),
    ]
    rows = [[
        f'<span style="font-weight:500;color:{INK2};">{k}</span>',
        f'<span style="color:{MUTED};">{v}</span>',
    ] for k, v in rows_data]

    return (
        f'<div class="ph">'
        f'<div class="ph-icon" style="background:{MUTED};">{I_INFO}</div>'
        f'<h2>About This Report</h2></div>'
        + _card(_table([], rows, ["28%", "72%"])
                + f'<div style="background:{AMBER_L};border-left:3px solid {AMBER};'
                f'border-radius:0 5px 5px 0;padding:10px 12px;margin-top:10px;">'
                f'<strong style="color:#92400E;font-size:12px;">⚠ Final Human Review Required</strong><br>'
                f'<span style="font-size:12px;color:#92400E;line-height:1.5;">'
                f'All AI-generated scores and recommendations require verification '
                f'before client delivery.</span>'
                f'</div>',
                I_INFO, "Report Details")
    )


def _cta():
    return (
        f'<div class="cta">'
        f'<p style="font-size:10px;font-weight:700;color:{SIDEBAR_MUT};'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">'
        f'Ready to act on these findings?</p>'
        f'<h2 style="font-size:20px;font-weight:700;color:#fff;'
        f'letter-spacing:-.2px;margin-bottom:8px;font-family:{F};">'
        f"Let's build your SEO growth engine.</h2>"
        f'<p style="font-size:13px;color:{SIDEBAR_TXT};max-width:380px;'
        f'margin:0 auto 20px;line-height:1.6;font-family:{F};">'
        f'Book a call to review findings, prioritize your roadmap, '
        f'and get a concrete plan for your Ottawa business.</p>'
        f'<a href="https://capitalai.ca/book" '
        f'style="display:inline-block;padding:11px 32px;background:{PRIMARY};'
        f'color:#fff;font-size:13px;font-weight:600;border-radius:6px;'
        f'text-decoration:none;font-family:{F};">'
        f'Book Your Follow-Up Call →</a>'
        f'<p style="margin-top:16px;font-size:11px;color:{SIDEBAR_MUT};">'
        f'CapitalAI.ca · Ottawa, ON · Privacy-first.</p>'
        f'</div>'
    )


# ── Document assembly ─────────────────────────────────────────────────────────

def _build(domain, client_data, competitor_data, gap_results,
           eeat_scores, technical, model):
    date_str = datetime.now().strftime("%B %d, %Y")
    now_iso  = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    sections = (
        f'<div class="gate">⚠️ '
        f'<strong>Human Review Required — </strong>'
        f'All findings require E-E-A-T Guardian approval before client delivery.'
        f'</div>'
        + _s_summary(domain, client_data, competitor_data, eeat_scores, technical)
        + '<div class="sep"></div>'
        + _s_eeat(eeat_scores, client_data)
        + '<div class="sep"></div>'
        + _s_gaps(gap_results, competitor_data)
        + '<div class="sep"></div>'
        + _s_technical(technical, client_data)
        + '<div class="sep"></div>'
        + _s_plan(eeat_scores, gap_results, technical)
        + '<div class="sep"></div>'
        + _s_about(domain, model)
    )

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>SEO Audit — {domain}</title>\n'
        f'<meta name="generator" content="CapitalAI-Audit-Crawler v1.0">\n'
        f'<meta name="date" content="{now_iso}">\n'
        + _css()
        + '</head>\n<body>\n'
        '<div class="shell">\n'
        + _sidebar(domain)
        + '<div class="main">\n'
        + _topbar(domain, date_str)
        + f'<div class="pc">{sections}</div>\n'
        + _cta()
        + '</div>\n'   # main
        '</div>\n'     # shell
        '</body>\n</html>'
    )


# ── Public entry point ────────────────────────────────────────────────────────

def write_html_report(
    domain: str,
    client_data: dict,
    competitor_data: dict,
    gap_results: dict,
    eeat_scores: dict,
    technical: dict,
    model: str = "llama3.1:8b",
    output_dir: str = "reports",
) -> str:
    """Generate a Sitemate-style SaaS dashboard HTML audit report."""
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_domain = domain.replace(".", "_").replace("/", "_")
    filepath    = Path(output_dir) / f"{safe_domain}_{timestamp}_audit.html"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    html = _build(domain, client_data, competitor_data,
                  gap_results, eeat_scores, technical, model)
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)
