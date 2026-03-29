# capitalai/output/pdf_writer.py
# CapitalAI Premium PDF Report Generator
# Engine: ReportLab (pure Python, zero system deps, works on Windows/Mac/Linux)
# Design: Dark-branded, emerald accents, premium agency aesthetic
# Usage: from capitalai.output.pdf_writer import write_pdf_report

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.colors import HexColor

# ─────────────────────────────────────────────────────────────────────────────
# Brand colours
# ─────────────────────────────────────────────────────────────────────────────
C_BG          = HexColor("#0d0d0d")   # CapitalAI bg   # Near-black background
C_SURFACE     = HexColor("#141414")   # CapitalAI surface   # Card surface
C_EMERALD     = HexColor("#C0392B")   # CapitalAI red   # Primary accent
C_EMERALD_DIM = HexColor("#7b1f1a")   # CapitalAI red dim   # Muted emerald
C_GOLD        = HexColor("#f59e0b")   # Warning / attention
C_RED         = HexColor("#ef4444")   # Critical
C_BLUE        = HexColor("#3b82f6")   # Info
C_WHITE       = HexColor("#f8fafc")   # Primary text
C_GREY        = HexColor("#94a3b8")   # Muted text
C_BORDER      = HexColor("#222222")   # CapitalAI border   # Subtle borders
C_COVER_BG    = HexColor("#0a0a0a")   # Pure black   # Cover page bg

PAGE_W, PAGE_H = A4
MARGIN        = 18 * mm
CONTENT_W     = PAGE_W - 2 * MARGIN


# ─────────────────────────────────────────────────────────────────────────────
# Custom flowables
# ─────────────────────────────────────────────────────────────────────────────

class EmeraldRule(Flowable):
    """A thin emerald horizontal rule."""
    def __init__(self, width=None, thickness=1.5):
        super().__init__()
        self.rule_width = width
        self.thickness  = thickness
        self.height     = thickness + 2

    def draw(self):
        w = self.rule_width or CONTENT_W
        self.canv.setStrokeColor(C_EMERALD)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.thickness / 2, w, self.thickness / 2)


class ScoreBar(Flowable):
    """Visual score bar: filled blocks + score label."""
    def __init__(self, score, out_of=10, width=120, label="", colour=None):
        super().__init__()
        try:
            self.score = float(score)
        except (TypeError, ValueError):
            self.score = 0.0
        self.out_of  = out_of
        self.bar_w   = width
        self.label   = label
        self.colour  = colour or self._auto_colour()
        self.height  = 14

    def _auto_colour(self):
        if self.score >= 7.5: return C_EMERALD
        if self.score >= 5.0: return C_GOLD
        return C_RED

    def draw(self):
        cell_w    = self.bar_w / self.out_of
        cell_h    = 10
        filled    = round(self.score)
        for i in range(self.out_of):
            x = i * cell_w
            if i < filled:
                self.canv.setFillColor(self.colour)
            else:
                self.canv.setFillColor(C_BORDER)
            self.canv.rect(x, 2, cell_w - 1.5, cell_h, fill=1, stroke=0)

        # Score label to the right
        self.canv.setFillColor(C_WHITE)
        self.canv.setFont("Helvetica-Bold", 8)
        self.canv.drawString(self.bar_w + 6, 4, f"{self.score}/{self.out_of}")

        # Optional label to the left
        if self.label:
            self.canv.setFillColor(C_GREY)
            self.canv.setFont("Helvetica", 7)
            self.canv.drawRightString(-4, 4, self.label)


class SectionChip(Flowable):
    """Coloured section number chip."""
    def __init__(self, number, title, width=CONTENT_W):
        super().__init__()
        self.number = str(number)
        self.title  = title
        self.width  = width
        self.height = 26

    def draw(self):
        # Background bar
        self.canv.setFillColor(C_SURFACE)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        # Emerald left accent
        self.canv.setFillColor(C_EMERALD)
        self.canv.rect(0, 0, 4, self.height, fill=1, stroke=0)
        # Number chip
        self.canv.setFillColor(C_EMERALD)
        self.canv.circle(18, 13, 9, fill=1, stroke=0)
        self.canv.setFillColor(C_BG)
        self.canv.setFont("Helvetica-Bold", 9)
        self.canv.drawCentredString(18, 10, self.number)
        # Title
        self.canv.setFillColor(C_WHITE)
        self.canv.setFont("Helvetica-Bold", 11)
        self.canv.drawString(34, 9, self.title)


class CoverFlowable(Flowable):
    """Full cover page drawn on canvas."""
    def __init__(self, domain, date_str, n_pages, n_competitors, overall_score):
        super().__init__()
        self.domain        = domain
        self.date_str      = date_str
        self.n_pages       = n_pages
        self.n_competitors = n_competitors
        self.overall_score = overall_score
        self.width         = PAGE_W
        self.height        = PAGE_H

    def draw(self):
        c = self.canv

        # ── Full-page dark background ──
        c.setFillColor(C_COVER_BG)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        # ── Emerald top accent bar ──
        c.setFillColor(C_EMERALD)
        c.rect(0, PAGE_H - 6, PAGE_W, 6, fill=1, stroke=0)

        # ── Subtle grid lines (decorative) ──
        c.setStrokeColor(HexColor("#1e2535"))
        c.setLineWidth(0.5)
        for y in range(0, int(PAGE_H), 40):
            c.line(0, y, PAGE_W, y)

        # ── Agency wordmark ──
        c.setFillColor(C_EMERALD)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(MARGIN, PAGE_H - 28, "CAPITALAI.CA")
        c.setFillColor(C_GREY)
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN, PAGE_H - 40, "Ottawa's Self-Hosted AI SEO Agency")

        # ── CONFIDENTIAL badge top right ──
        badge_x = PAGE_W - MARGIN - 90
        c.setFillColor(HexColor("#1e2535"))
        c.roundRect(badge_x, PAGE_H - 44, 90, 18, 3, fill=1, stroke=0)
        c.setStrokeColor(C_EMERALD_DIM)
        c.setLineWidth(0.8)
        c.roundRect(badge_x, PAGE_H - 44, 90, 18, 3, fill=0, stroke=1)
        c.setFillColor(C_GREY)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(badge_x + 45, PAGE_H - 34, "⚠  CONFIDENTIAL — REVIEW BEFORE DELIVERY")

        # ── Main title block ──
        title_y = PAGE_H * 0.62
        c.setFillColor(C_WHITE)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(MARGIN, title_y, "SEO AUDIT REPORT")

        c.setFillColor(C_EMERALD)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(MARGIN, title_y - 24, self.domain)

        c.setFillColor(C_GREY)
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, title_y - 42, f"Prepared: {self.date_str}")

        # ── Divider ──
        c.setStrokeColor(C_EMERALD)
        c.setLineWidth(1.5)
        c.line(MARGIN, title_y - 52, PAGE_W - MARGIN, title_y - 52)

        # ── Stat boxes ──
        box_y   = title_y - 110
        box_h   = 50
        box_w   = (CONTENT_W - 10) / 3
        stats   = [
            ("Pages Audited",    str(self.n_pages),       C_BLUE),
            ("Competitors",      str(self.n_competitors), C_GOLD),
            ("E-E-A-T Score",    f"{self.overall_score}/10",
             C_EMERALD if float(self.overall_score or 0) >= 7.5
             else C_GOLD if float(self.overall_score or 0) >= 5.0 else C_RED),
        ]
        for i, (label, value, colour) in enumerate(stats):
            bx = MARGIN + i * (box_w + 5)
            c.setFillColor(C_SURFACE)
            c.roundRect(bx, box_y, box_w, box_h, 5, fill=1, stroke=0)
            c.setStrokeColor(colour)
            c.setLineWidth(1)
            c.roundRect(bx, box_y, box_w, box_h, 5, fill=0, stroke=1)
            c.setFillColor(colour)
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(bx + box_w / 2, box_y + 22, value)
            c.setFillColor(C_GREY)
            c.setFont("Helvetica", 8)
            c.drawCentredString(bx + box_w / 2, box_y + 11, label.upper())

        # ── Footer ──
        c.setFillColor(C_EMERALD)
        c.rect(0, 0, PAGE_W, 4, fill=1, stroke=0)
        c.setFillColor(C_GREY)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, 12, "Powered by Crawl4AI + Ollama llama3.1:8b — 100% local, zero cloud")
        c.drawRightString(PAGE_W - MARGIN, 12, "capitalai.ca")


# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()

    def S(name, **kw):
        defaults = dict(
            fontName="Helvetica",
            fontSize=10,
            textColor=C_WHITE,
            backColor=None,
            leading=15,
            spaceAfter=6,
        )
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    return {
        "h1":       S("h1",  fontName="Helvetica-Bold", fontSize=18, textColor=C_WHITE,
                      spaceBefore=14, spaceAfter=6),
        "h2":       S("h2",  fontName="Helvetica-Bold", fontSize=13, textColor=C_EMERALD,
                      spaceBefore=12, spaceAfter=4),
        "h3":       S("h3",  fontName="Helvetica-Bold", fontSize=11, textColor=C_WHITE,
                      spaceBefore=8,  spaceAfter=3),
        "body":     S("body", fontSize=9,  textColor=C_GREY,  leading=14, spaceAfter=5),
        "bold":     S("bold", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE),
        "caption":  S("caption", fontSize=8, textColor=C_GREY, leading=12, spaceAfter=3),
        "excerpt":  S("excerpt", fontSize=9, textColor=C_GREY, leading=14,
                      leftIndent=10, rightIndent=10, spaceAfter=5,
                      borderPad=6, borderColor=C_EMERALD_DIM, borderWidth=0),
        "label":    S("label", fontName="Helvetica-Bold", fontSize=8,
                      textColor=C_EMERALD, leading=10, spaceAfter=2),
        "warning":  S("warning", fontName="Helvetica-Bold", fontSize=9,
                      textColor=C_GOLD, leading=13),
        "center":   S("center", fontSize=9, alignment=TA_CENTER, textColor=C_GREY),
        "url":      S("url",   fontName="Helvetica-Oblique", fontSize=8,
                      textColor=C_BLUE, leading=12),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page template (header/footer on every page except cover)
# ─────────────────────────────────────────────────────────────────────────────

class _PageNumCanvas:
    """Mixin for page numbers — attached via BaseDocTemplate."""
    pass


def _on_page(canvas, doc):
    """Draw running header + footer on every content page."""
    if doc.page == 1:
        return  # Skip cover page
    canvas.saveState()
    # Header
    canvas.setFillColor(C_EMERALD)
    canvas.rect(0, PAGE_H - 10, PAGE_W, 10, fill=1, stroke=0)
    canvas.setFillColor(C_GREY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, PAGE_H - 21, f"SEO Audit — {doc.domain}")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 21, "CONFIDENTIAL — Review before delivery")
    # Footer
    canvas.setFillColor(C_EMERALD)
    canvas.rect(0, 0, PAGE_W, 4, fill=1, stroke=0)
    canvas.setFillColor(C_GREY)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 8, "CapitalAI.ca — Ottawa's Self-Hosted AI SEO Agency")
    canvas.drawRightString(PAGE_W - MARGIN, 8, f"Page {doc.page}")
    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# Table helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dark_table(data, col_widths, header=True, stripe=True):
    """Build a consistently styled dark-theme table."""
    ts = [
        ("BACKGROUND",  (0, 0), (-1, 0 if header else -1), C_SURFACE),
        ("TEXTCOLOR",   (0, 0), (-1, -1),  C_GREY),
        ("FONTNAME",    (0, 0), (-1, -1),  "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1),  8),
        ("TOPPADDING",  (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING",(0,0), (-1, -1),  5),
        ("LEFTPADDING", (0, 0), (-1, -1),  7),
        ("RIGHTPADDING",(0, 0), (-1, -1),  7),
        ("LINEBELOW",   (0, 0), (-1, -1),  0.4, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_BG, C_SURFACE] if stripe else [C_BG]),
    ]
    if header:
        ts += [
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  C_EMERALD),
            ("BACKGROUND",  (0, 0), (-1, 0),  HexColor("#0d2218")),
            ("LINEBELOW",   (0, 0), (-1, 0),  1.0, C_EMERALD),
        ]
    return Table(data, colWidths=col_widths, style=TableStyle(ts), repeatRows=1 if header else 0)


def _score_colour(score):
    try:
        s = float(score)
        if s >= 7.5: return C_EMERALD
        if s >= 5.0: return C_GOLD
        return C_RED
    except (TypeError, ValueError):
        return C_GREY


def _score_text(score):
    try:
        s = float(score)
        return f"{s}/10"
    except (TypeError, ValueError):
        return "N/A"


def _severity_colour(count):
    try:
        n = int(count)
        if n == 0: return C_EMERALD
        if n <= 2:  return C_GOLD
        return C_RED
    except (TypeError, ValueError):
        return C_GREY


# ─────────────────────────────────────────────────────────────────────────────
# Content excerpt helper
# ─────────────────────────────────────────────────────────────────────────────

def _excerpt(page: dict, max_words: int = 35) -> str:
    body = page.get("body_excerpt", "") or ""
    words = body.split()
    if not words:
        return ""
    chunk = " ".join(words[:max_words])
    if len(words) > max_words:
        chunk += "…"
    return chunk


# ─────────────────────────────────────────────────────────────────────────────
# Section builders — return list of Flowables
# ─────────────────────────────────────────────────────────────────────────────

def _cover(domain, date_str, n_pages, n_competitors, overall_score, S):
    overall = overall_score if overall_score is not None else "N/A"
    return [
        CoverFlowable(domain, date_str, n_pages, n_competitors, overall),
        PageBreak(),
    ]


def _section_toc(S):
    """Table of contents."""
    items = [
        ("1", "Executive Summary"),
        ("2", "E-E-A-T Scorecard"),
        ("3", "Content Gap Analysis"),
        ("4", "Technical SEO Health"),
        ("5", "Prioritized Action Plan"),
        ("6", "About This Report"),
    ]
    story = [
        SectionChip("→", "Table of Contents"),
        Spacer(1, 10),
    ]
    for num, title in items:
        story.append(Paragraph(
            f'<font color="#10b981"><b>{num}.</b></font>'
            f'<font color="#94a3b8">  {title}</font>',
            S["body"]
        ))
    story += [Spacer(1, 6), EmeraldRule(), Spacer(1, 12)]
    return story


def _section_human_gate(S):
    data = [[
        Paragraph("⚠  HUMAN REVIEW GATE", ParagraphStyle(
            "warn_hd", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_GOLD, leading=13)),
        Paragraph(
            "This report was generated by the CapitalAI autonomous audit engine. "
            "All findings, scores, and recommendations must be reviewed and approved "
            "by the E-E-A-T Guardian before sharing with any client. "
            "Do not deliver externally before sign-off.",
            ParagraphStyle("warn_body", fontName="Helvetica", fontSize=8,
                           textColor=C_GREY, leading=13))
    ]]
    t = Table(data, colWidths=[52*mm, CONTENT_W - 52*mm],
              style=TableStyle([
                  ("BACKGROUND",    (0,0),(-1,-1), HexColor("#1a1200")),
                  ("LINEBELOW",     (0,0),(-1,-1), 0.8, C_GOLD),
                  ("LINETOP",       (0,0),(-1,-1), 0.8, C_GOLD),
                  ("LINEBEFORE",    (0,0),(0,-1),  2.5, C_GOLD),
                  ("LINEAFTER",     (-1,0),(-1,-1), 0.8, C_GOLD),
                  ("TOPPADDING",    (0,0),(-1,-1), 8),
                  ("BOTTOMPADDING", (0,0),(-1,-1), 8),
                  ("LEFTPADDING",   (0,0),(-1,-1), 8),
                  ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                  ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
              ]))
    return [t, Spacer(1, 14)]


def _section_exec_summary(domain, client_data, competitor_data, eeat_scores, technical, S):
    agg     = eeat_scores.get("site_aggregate", {})
    tech    = technical.get("summary", {})
    overall = agg.get("overall_score", "N/A")
    n_pages = len(client_data)
    n_comps = len(competitor_data)
    issues  = tech.get("missing_meta", 0) + tech.get("h1_issues", 0) + tech.get("no_schema_pages", 0)

    try:
        o = float(overall)
        health_text  = "Strong" if o >= 7.5 else ("Needs Work" if o >= 5.0 else "Needs Immediate Attention")
        health_col   = C_EMERALD if o >= 7.5 else (C_GOLD if o >= 5.0 else C_RED)
    except (TypeError, ValueError):
        health_text, health_col = "Not Scored", C_GREY

    story = [
        SectionChip("1", "Executive Summary"),
        Spacer(1, 10),
        Paragraph(
            f"We audited <b>{n_pages} pages</b> on <b>{domain}</b>"
            + (f" and compared them against <b>{n_comps} competitor site(s)</b>." if n_comps else "."),
            S["body"]
        ),
        Spacer(1, 8),
    ]

    # KPI row
    kpi_data = [
        ["OVERALL HEALTH", "E-E-A-T SCORE", "TECHNICAL ISSUES", "COMPETITORS"],
        [health_text, f"{overall}/10", str(issues), str(n_comps)],
    ]
    kpi_widths = [CONTENT_W / 4] * 4
    kpi_style  = TableStyle([
        ("BACKGROUND",     (0,0),(-1,0),  C_SURFACE),
        ("BACKGROUND",     (0,1),(-1,1),  C_BG),
        ("TEXTCOLOR",      (0,0),(-1,0),  C_GREY),
        ("TEXTCOLOR",      (0,1),(-1,1),  C_WHITE),
        ("FONTNAME",       (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTNAME",       (0,1),(-1,1),  "Helvetica-Bold"),
        ("FONTSIZE",       (0,0),(-1,0),  7),
        ("FONTSIZE",       (0,1),(-1,1),  16),
        ("ALIGN",          (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",     (0,0),(-1,-1), 8),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 8),
        ("LINEBEFORE",     (1,0),(3,-1),  0.5, C_BORDER),
        ("LINEBELOW",      (0,0),(-1,-1), 0.4, C_BORDER),
        ("TEXTCOLOR",      (0,1),(0,1),   health_col),
        ("TEXTCOLOR",      (1,1),(1,1),   _score_colour(overall)),
        ("TEXTCOLOR",      (2,1),(2,1),   C_RED if issues > 0 else C_EMERALD),
    ])
    story += [Table(kpi_data, colWidths=kpi_widths, style=kpi_style), Spacer(1, 10)]

    # Verdict
    verdict = agg.get("verdict", "")
    if verdict:
        story += [
            Paragraph("Bottom Line", S["label"]),
            Paragraph(verdict, S["body"]),
            Spacer(1, 6),
        ]

    # Worst page callout
    page_scores = eeat_scores.get("page_scores", {})
    worst_url, worst_s, worst_score = None, {}, 10.0
    for url, s in page_scores.items():
        if "parse_error" not in s:
            try:
                sc = float(s.get("overall_score", 10))
                if sc < worst_score:
                    worst_score, worst_url, worst_s = sc, url, s
            except (TypeError, ValueError):
                pass

    if worst_url:
        callout_data = [[
            Paragraph("Most Critical Finding", ParagraphStyle(
                "cf_hd", fontName="Helvetica-Bold", fontSize=8,
                textColor=C_RED, leading=12)),
            Paragraph(
                f"<b>{worst_url}</b> scored <b>{worst_score}/10</b>. "
                f"{worst_s.get('top_issue','N/A')} "
                f"<i>Fix: {worst_s.get('quick_fix','N/A')}</i>",
                ParagraphStyle("cf_body", fontName="Helvetica", fontSize=8,
                               textColor=C_GREY, leading=13))
        ]]
        story.append(Table(callout_data, colWidths=[38*mm, CONTENT_W-38*mm],
                           style=TableStyle([
                               ("BACKGROUND",    (0,0),(-1,-1), HexColor("#1a0a0a")),
                               ("LINEBEFORE",    (0,0),(0,-1),  2.5, C_RED),
                               ("TOPPADDING",    (0,0),(-1,-1), 7),
                               ("BOTTOMPADDING", (0,0),(-1,-1), 7),
                               ("LEFTPADDING",   (0,0),(-1,-1), 8),
                               ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                               ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                           ])))
        story.append(Spacer(1, 4))

    story += [Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
    return story


def _section_eeat(eeat_scores, client_data, S):
    agg         = eeat_scores.get("site_aggregate", {})
    page_scores = eeat_scores.get("page_scores", {})

    story = [
        SectionChip("2", "E-E-A-T Scorecard"),
        Spacer(1, 8),
        Paragraph(
            "Google's E-E-A-T framework (Experience, Expertise, Authoritativeness, Trustworthiness) "
            "is the primary lens for content quality evaluation. Low E-E-A-T is the #1 cause "
            "of ranking suppression under the Helpful Content system.",
            S["body"]
        ),
        Spacer(1, 10),
    ]

    if not agg or "error" in agg:
        story += [Paragraph("E-E-A-T scoring was skipped for this run.", S["warning"]),
                  Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
        return story

    # ── Scorecard table with inline bars ──
    dims = [
        ("Experience",        agg.get("experience",        0), "Real first-hand signals"),
        ("Expertise",         agg.get("expertise",         0), "Subject-matter depth"),
        ("Authoritativeness", agg.get("authoritativeness", 0), "Author bios, citations"),
        ("Trustworthiness",   agg.get("trustworthiness",   0), "Contact info, HTTPS, privacy"),
    ]
    overall = agg.get("overall_score", 0)

    card_data = [["Dimension", "Score", "Visual", "What It Means"]]
    for label, score, meaning in dims:
        card_data.append([
            Paragraph(f"<b>{label}</b>", ParagraphStyle(
                "dim_lbl", fontName="Helvetica-Bold", fontSize=8, textColor=C_WHITE)),
            Paragraph(f"<b>{_score_text(score)}</b>", ParagraphStyle(
                "dim_sc", fontName="Helvetica-Bold", fontSize=9,
                textColor=_score_colour(score), alignment=TA_CENTER)),
            ScoreBar(score, width=80),
            Paragraph(meaning, ParagraphStyle(
                "dim_mn", fontName="Helvetica", fontSize=8, textColor=C_GREY, leading=12)),
        ])

    # Overall row
    card_data.append([
        Paragraph("<b>⭐ OVERALL</b>", ParagraphStyle(
            "ov_lbl", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
        Paragraph(f"<b>{_score_text(overall)}</b>", ParagraphStyle(
            "ov_sc", fontName="Helvetica-Bold", fontSize=11,
            textColor=_score_colour(overall), alignment=TA_CENTER)),
        ScoreBar(overall, width=80),
        Paragraph(agg.get("rating", ""), ParagraphStyle(
            "ov_rt", fontName="Helvetica-Bold", fontSize=9,
            textColor=_score_colour(overall))),
    ])

    col_w = [45*mm, 22*mm, 42*mm, CONTENT_W - 45*mm - 22*mm - 42*mm]
    ts    = TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),    HexColor("#0d2218")),
        ("TEXTCOLOR",     (0,0),(-1,0),    C_EMERALD),
        ("FONTNAME",      (0,0),(-1,0),    "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),    8),
        ("LINEBELOW",     (0,0),(-1,0),    1.0, C_EMERALD),
        ("ROWBACKGROUNDS",(0,1),(-1,-2),   [C_BG, C_SURFACE]),
        ("BACKGROUND",    (0,-1),(-1,-1),  HexColor("#0d2218")),
        ("LINEABOVE",     (0,-1),(-1,-1),  1.0, C_EMERALD),
        ("TOPPADDING",    (0,0),(-1,-1),   7),
        ("BOTTOMPADDING", (0,0),(-1,-1),   7),
        ("LEFTPADDING",   (0,0),(-1,-1),   7),
        ("RIGHTPADDING",  (0,0),(-1,-1),   7),
        ("VALIGN",        (0,0),(-1,-1),   "MIDDLE"),
        ("ALIGN",         (1,0),(1,-1),    "CENTER"),
    ])
    story += [Table(card_data, colWidths=col_w, style=ts), Spacer(1, 14)]

    # ── Page-level breakdown ──
    weak   = [(u, s) for u, s in page_scores.items()
              if "parse_error" not in s and float(s.get("overall_score", 10) or 10) < 6.0]
    strong = [(u, s) for u, s in page_scores.items()
              if "parse_error" not in s and float(s.get("overall_score", 0) or 0) >= 6.0]
    weak.sort(key=lambda x: float(x[1].get("overall_score", 10) or 10))

    if weak:
        story += [
            Paragraph("Pages Needing Immediate Attention", S["h2"]),
            Paragraph(
                "These pages are suppressing your site's overall E-E-A-T signal. "
                "Each is a ranking liability until addressed.",
                S["body"]
            ),
            Spacer(1, 6),
        ]
        for url, sc in weak[:6]:
            page    = client_data.get(url, {})
            ex      = _excerpt(page, 30)
            score_v = sc.get("overall_score", "?")
            issue   = sc.get("top_issue",     "N/A")
            fix     = sc.get("quick_fix",     "N/A")
            wc      = page.get("word_count",  "?")

            page_block = [
                [
                    Paragraph(f"<b>{url}</b>", ParagraphStyle(
                        "pu", fontName="Helvetica-Bold", fontSize=8,
                        textColor=C_BLUE, leading=12)),
                    Paragraph(
                        f"Score: <b><font color='{'#10b981' if float(score_v or 0) >= 7.5 else '#f59e0b' if float(score_v or 0) >= 5 else '#ef4444'}'>"
                        f"{score_v}/10</font></b>  |  Words: {wc}",
                        ParagraphStyle("psc", fontName="Helvetica", fontSize=8,
                                       textColor=C_GREY, leading=12, alignment=TA_RIGHT)),
                ],
            ]
            inner_ts = TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), HexColor("#0d1526")),
                ("TOPPADDING",   (0,0),(-1,-1), 5),
                ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                ("LEFTPADDING",  (0,0),(-1,-1), 7),
                ("RIGHTPADDING", (0,0),(-1,-1), 7),
            ])
            story.append(Table(page_block, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35],
                               style=inner_ts))

            details = []
            if ex:
                details.append(Paragraph(f'<i>"{ex}"</i>', ParagraphStyle(
                    "ex", fontName="Helvetica-Oblique", fontSize=8,
                    textColor=HexColor("#64748b"), leading=13,
                    leftIndent=8, rightIndent=8, spaceAfter=3)))
            details.append(Paragraph(
                f"<b>Issue:</b> {issue}",
                ParagraphStyle("iss", fontName="Helvetica", fontSize=8,
                               textColor=C_GREY, leading=13, leftIndent=8)))
            details.append(Paragraph(
                f"<b>Fix:</b> {fix}",
                ParagraphStyle("fix", fontName="Helvetica-Bold", fontSize=8,
                               textColor=C_EMERALD, leading=13, leftIndent=8)))

            detail_block = [[d] for d in details]
            detail_ts = TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), C_BG),
                ("TOPPADDING",   (0,0),(-1,-1), 3),
                ("BOTTOMPADDING",(0,0),(-1,-1), 3),
                ("LEFTPADDING",  (0,0),(-1,-1), 7),
                ("RIGHTPADDING", (0,0),(-1,-1), 7),
                ("LINEBEFORE",   (0,0),(0,-1),  2, _score_colour(score_v)),
            ])
            story.append(Table([[d] for d in details], colWidths=[CONTENT_W],
                               style=detail_ts))
            story.append(Spacer(1, 6))

    if strong:
        story += [
            Paragraph("Strong Pages — Protect &amp; Amplify", S["h2"]),
            Spacer(1, 4),
        ]
        strong_data = [["Page", "Score", "Action"]]
        for url, sc in strong[:5]:
            strong_data.append([
                Paragraph(url, ParagraphStyle("su", fontName="Helvetica", fontSize=7,
                                              textColor=C_BLUE, leading=11)),
                Paragraph(f"<b>{_score_text(sc.get('overall_score'))}</b>",
                          ParagraphStyle("ss", fontName="Helvetica-Bold", fontSize=8,
                                         textColor=C_EMERALD, alignment=TA_CENTER)),
                Paragraph("Internal link target. Add to sitemap priority.",
                          ParagraphStyle("sa", fontName="Helvetica", fontSize=7,
                                         textColor=C_GREY, leading=11)),
            ])
        story.append(_dark_table(strong_data, [CONTENT_W*0.55, 22*mm, CONTENT_W*0.35]))
        story.append(Spacer(1, 6))

    story += [Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
    return story


def _section_gaps(gap_results, competitor_data, S):
    gaps      = gap_results.get("content_gaps", [])
    opps      = gap_results.get("content_opportunities", [])
    strengths = gap_results.get("unique_strengths", [])

    story = [
        SectionChip("3", "Content Gap Analysis"),
        Spacer(1, 8),
    ]

    if gap_results.get("note") == "No competitor data.":
        story += [Paragraph("No competitor URLs were provided. Re-run with --competitors.", S["body"]),
                  Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
        return story

    story.append(Paragraph(
        f"We identified <b>{len(gaps)} topic gaps</b> where competitors rank and you don't — "
        f"each representing uncontested traffic your site is currently missing.",
        S["body"]
    ))
    story.append(Spacer(1, 10))

    # Gaps table
    if gaps:
        story.append(Paragraph("Topics Your Competitors Own — You Don't", S["h2"]))
        gap_data = [["#", "Missing Topic", "Priority"]]
        for i, g in enumerate(gaps[:15], 1):
            pri = "HIGH" if i <= 5 else ("MEDIUM" if i <= 10 else "LOW")
            pri_col = C_RED if pri == "HIGH" else (C_GOLD if pri == "MEDIUM" else C_GREY)
            gap_data.append([
                Paragraph(str(i), ParagraphStyle("gn", fontName="Helvetica-Bold",
                                                  fontSize=9, textColor=C_EMERALD,
                                                  alignment=TA_CENTER)),
                Paragraph(g, ParagraphStyle("gt", fontName="Helvetica", fontSize=8,
                                             textColor=C_WHITE, leading=12)),
                Paragraph(f"<b>{pri}</b>", ParagraphStyle("gp", fontName="Helvetica-Bold",
                                                            fontSize=7, textColor=pri_col,
                                                            alignment=TA_CENTER)),
            ])
        story.append(_dark_table(gap_data, [12*mm, CONTENT_W - 30*mm, 18*mm]))
        story.append(Spacer(1, 10))

    # Opportunities
    if opps:
        story += [
            Paragraph("Top Content Opportunities", S["h2"]),
            Paragraph("Highest-ROI pages to create first — based on gap severity and search intent.",
                      S["body"]),
            Spacer(1, 6),
        ]
        for i, opp in enumerate(opps[:5], 1):
            opp_block = [
                Paragraph(f"Opportunity {i}", ParagraphStyle(
                    "on", fontName="Helvetica-Bold", fontSize=7,
                    textColor=C_EMERALD, leading=10)),
                Paragraph(f"<b>{opp.strip().rstrip('.')}</b>", ParagraphStyle(
                    "ot", fontName="Helvetica-Bold", fontSize=9,
                    textColor=C_WHITE, leading=13)),
                Paragraph(
                    f"Suggested approach: Create a 1,200+ word pillar page targeting this topic. "
                    f"Include LocalBusiness or Article schema. Add to internal link cluster.",
                    ParagraphStyle("ob", fontName="Helvetica", fontSize=8,
                                   textColor=C_GREY, leading=13)),
            ]
            opp_rows = [[b] for b in opp_block]
            opp_ts   = TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), C_SURFACE),
                ("LINEBEFORE",   (0,0),(0,-1),  3, C_EMERALD),
                ("TOPPADDING",   (0,0),(-1,-1), 5),
                ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                ("LEFTPADDING",  (0,0),(-1,-1), 10),
                ("RIGHTPADDING", (0,0),(-1,-1), 10),
            ])
            story.append(Table(opp_rows, colWidths=[CONTENT_W], style=opp_ts))
            story.append(Spacer(1, 5))

    # Strengths
    if strengths:
        story += [
            Spacer(1, 6),
            Paragraph("Your Competitive Advantages", S["h2"]),
            Paragraph("Double down here — internal links, updated content, schema.", S["body"]),
            Spacer(1, 4),
        ]
        str_data = [[
            Paragraph(s, ParagraphStyle("st", fontName="Helvetica", fontSize=8,
                                         textColor=C_WHITE, leading=12))
        ] for s in strengths[:8]]
        str_ts = TableStyle([
            ("ROWBACKGROUNDS", (0,0),(-1,-1), [C_BG, C_SURFACE]),
            ("TOPPADDING",     (0,0),(-1,-1), 5),
            ("BOTTOMPADDING",  (0,0),(-1,-1), 5),
            ("LEFTPADDING",    (0,0),(-1,-1), 10),
            ("RIGHTPADDING",   (0,0),(-1,-1), 10),
            ("LINEBELOW",      (0,0),(-1,-1), 0.3, C_BORDER),
        ])
        story.append(Table(str_data, colWidths=[CONTENT_W], style=str_ts))

    # Competitor snapshot
    if competitor_data:
        story += [Spacer(1, 10), Paragraph("Competitor Snapshot", S["h2"])]
        comp_data = [["Competitor URL", "Pages Crawled"]]
        for url, pages in competitor_data.items():
            comp_data.append([
                Paragraph(url, ParagraphStyle("cu", fontName="Helvetica", fontSize=8,
                                               textColor=C_BLUE, leading=12)),
                Paragraph(str(len(pages)), ParagraphStyle("cp", fontName="Helvetica-Bold",
                                                            fontSize=9, textColor=C_WHITE,
                                                            alignment=TA_CENTER)),
            ])
        story.append(_dark_table(comp_data, [CONTENT_W - 30*mm, 30*mm]))

    story += [Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
    return story


def _section_technical(technical, client_data, S):
    tech  = technical.get("summary", {})
    rows  = [
        ("Missing meta descriptions", tech.get("missing_meta",       0), "Hurts CTR — Google writes them badly for you"),
        ("H1 tag issues",             tech.get("h1_issues",          0), "Confuses crawlers on page topic"),
        ("Images missing alt text",   tech.get("alt_tag_issues",     0), "Accessibility + image search loss"),
        ("Pages without schema",      tech.get("no_schema_pages",    0), "Missing rich result eligibility"),
        ("Thin content (<300 words)", tech.get("thin_pages",         0), "E-E-A-T risk under Helpful Content"),
        ("Missing canonical tags",    tech.get("missing_canonical",  0), "Duplicate content risk"),
    ]
    total_issues = sum(r[1] for r in rows)

    story = [
        SectionChip("4", "Technical SEO Health"),
        Spacer(1, 8),
        Paragraph(
            f"Scanned <b>{tech.get('total_pages', len(client_data))} pages</b>. "
            f"Found <b>{total_issues} technical issues</b> that directly impact "
            "crawlability, indexability, and ranking potential.",
            S["body"]
        ),
        Spacer(1, 10),
    ]

    # Issue table
    tdata = [["Issue", "Count", "Severity", "Why It Matters"]]
    for label, count, impact in rows:
        sev = "NONE" if count == 0 else ("HIGH" if count > 2 else "LOW")
        sev_col = C_EMERALD if count == 0 else (C_RED if count > 2 else C_GOLD)
        tdata.append([
            Paragraph(label, ParagraphStyle("tl", fontName="Helvetica", fontSize=8,
                                             textColor=C_WHITE, leading=12)),
            Paragraph(f"<b>{count}</b>", ParagraphStyle("tc", fontName="Helvetica-Bold",
                                                          fontSize=10, textColor=_severity_colour(count),
                                                          alignment=TA_CENTER)),
            Paragraph(f"<b>{sev}</b>", ParagraphStyle("ts", fontName="Helvetica-Bold",
                                                        fontSize=7, textColor=sev_col,
                                                        alignment=TA_CENTER)),
            Paragraph(impact, ParagraphStyle("ti", fontName="Helvetica", fontSize=8,
                                              textColor=C_GREY, leading=12)),
        ])
    story.append(_dark_table(tdata, [52*mm, 18*mm, 20*mm, CONTENT_W - 90*mm]))
    story.append(Spacer(1, 10))

    # Schema opportunities
    schema_opps = technical.get("schema_opportunities", [])
    if schema_opps:
        story += [
            Paragraph("Schema Markup Opportunities", S["h2"]),
            Paragraph(
                "Schema enables rich results (star ratings, FAQs, breadcrumbs). "
                "Every page below is currently invisible to these features.",
                S["body"]
            ),
            Spacer(1, 6),
        ]
        sdata = [["Page", "Add Schema", "Reason"]]
        for opp in schema_opps:
            sdata.append([
                Paragraph(opp.get("url", ""), ParagraphStyle("su2", fontName="Helvetica",
                                                               fontSize=7, textColor=C_BLUE,
                                                               leading=11)),
                Paragraph(f"<b>{opp.get('priority_schema','?')}</b>",
                          ParagraphStyle("sst", fontName="Helvetica-Bold", fontSize=8,
                                         textColor=C_EMERALD, alignment=TA_CENTER)),
                Paragraph(opp.get("reason", ""), ParagraphStyle("sr", fontName="Helvetica",
                                                                  fontSize=8, textColor=C_GREY,
                                                                  leading=12)),
            ])
        story.append(_dark_table(sdata, [CONTENT_W*0.45, 28*mm, CONTENT_W*0.40]))
        story.append(Spacer(1, 6))

    # Thin content list
    thin = technical.get("thin_content", [])
    if thin:
        story += [
            Paragraph("Thin Content Pages", S["h2"]),
            Spacer(1, 4),
        ]
        thin_data = [["Page", "Words", "Action"]]
        for item in thin[:8]:
            wc  = item.get("word_count", 0)
            rec = "Expand to 800+ words" if wc > 100 else "Consolidate or noindex"
            thin_data.append([
                Paragraph(item.get("url", ""), ParagraphStyle("thu", fontName="Helvetica",
                                                                fontSize=7, textColor=C_BLUE,
                                                                leading=11)),
                Paragraph(str(wc), ParagraphStyle("thw", fontName="Helvetica-Bold", fontSize=9,
                                                    textColor=C_GOLD, alignment=TA_CENTER)),
                Paragraph(rec, ParagraphStyle("thr", fontName="Helvetica", fontSize=8,
                                               textColor=C_GREY, leading=12)),
            ])
        story.append(_dark_table(thin_data, [CONTENT_W*0.55, 20*mm, CONTENT_W*0.35]))

    story += [Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
    return story


def _section_action_plan(eeat_scores, gap_results, technical, S):
    tech          = technical.get("summary", {})
    missing_meta  = tech.get("missing_meta",      0)
    h1_issues     = tech.get("h1_issues",         0)
    no_schema     = tech.get("no_schema_pages",   0)
    thin_pages    = tech.get("thin_pages",        0)
    gaps          = gap_results.get("content_gaps", [])
    opps          = gap_results.get("content_opportunities", [])
    page_scores   = eeat_scores.get("page_scores", {})
    critical_count = sum(
        1 for s in page_scores.values()
        if "parse_error" not in s and float(s.get("overall_score", 10) or 10) < 5.0
    )

    story = [
        SectionChip("5", "Prioritized Action Plan"),
        Spacer(1, 8),
        Paragraph("Tasks ordered by ROI impact. Complete in sequence for maximum compounding effect.", S["body"]),
        Spacer(1, 10),
    ]

    phases = [
        ("🔴  WEEK 1 — Fix the Foundation", C_RED, [
            (f"Write meta descriptions for {missing_meta} page(s)" if missing_meta > 0
             else "✅ Meta descriptions complete",
             "Direct CTR impact — 30 min per page",
             C_RED if missing_meta > 0 else C_EMERALD),
            (f"Fix H1 tags on {h1_issues} page(s)" if h1_issues > 0
             else "✅ H1 tags healthy",
             "Critical for crawler topic understanding",
             C_RED if h1_issues > 0 else C_EMERALD),
            (f"Emergency E-E-A-T repair on {critical_count} critical page(s)" if critical_count > 0
             else "✅ No critical E-E-A-T pages",
             "Add author bio, trust signals, verifiable source",
             C_RED if critical_count > 0 else C_EMERALD),
        ]),
        ("🟡  MONTH 1 — Build Authority", C_GOLD, [
            (f"Add schema markup to {no_schema} unstructured page(s)",
             "Unlock rich result eligibility", C_GOLD),
            (f"Expand {thin_pages} thin content page(s) to 800+ words",
             "Reduce Helpful Content demotion risk", C_GOLD),
            ("Add author bio block to all content pages",
             "Single highest-ROI E-E-A-T fix", C_GOLD),
            ("Internal link audit — connect strong pages to weak ones",
             "Distribute E-E-A-T authority across the site", C_GOLD),
        ]),
        ("🟢  MONTH 2–3 — Scale & Dominate", C_EMERALD, [
            (f"Create {min(len(opps),5)} new pillar pages from content opportunities",
             "Close identified traffic gaps", C_EMERALD),
            (f"Close {len(gaps)} content gaps with targeted articles",
             "Assign each gap to a writer with brief + schema requirements", C_EMERALD),
            ("Geo-programmatic expansion — Ottawa neighbourhoods + NCR service areas",
             "KrispCall/Flyhomes-style scale play", C_EMERALD),
            ("Weekly freshness automation via n8n",
             "Maintain ranking momentum with updated content signals", C_EMERALD),
            ("AI citation targeting — restructure top pages as answer capsules",
             "Target Perplexity, ChatGPT, Claude citations", C_EMERALD),
        ]),
    ]

    for phase_title, phase_col, tasks in phases:
        story.append(Paragraph(phase_title, ParagraphStyle(
            "ph", fontName="Helvetica-Bold", fontSize=10,
            textColor=phase_col, spaceBefore=10, spaceAfter=4)))

        task_data = []
        for task, detail, col in tasks:
            task_data.append([
                Paragraph("☐", ParagraphStyle("cb", fontName="Helvetica", fontSize=10,
                                               textColor=col, alignment=TA_CENTER,
                                               leading=14)),
                Paragraph(f"<b>{task}</b>", ParagraphStyle("tt", fontName="Helvetica-Bold",
                                                             fontSize=8, textColor=C_WHITE,
                                                             leading=13)),
                Paragraph(detail, ParagraphStyle("td", fontName="Helvetica", fontSize=8,
                                                  textColor=C_GREY, leading=13)),
            ])
        story.append(Table(task_data, colWidths=[10*mm, 70*mm, CONTENT_W - 80*mm],
                           style=TableStyle([
                               ("ROWBACKGROUNDS", (0,0),(-1,-1), [C_BG, C_SURFACE]),
                               ("TOPPADDING",     (0,0),(-1,-1), 6),
                               ("BOTTOMPADDING",  (0,0),(-1,-1), 6),
                               ("LEFTPADDING",    (0,0),(-1,-1), 6),
                               ("RIGHTPADDING",   (0,0),(-1,-1), 6),
                               ("ALIGN",          (0,0),(0,-1),  "CENTER"),
                               ("VALIGN",         (0,0),(-1,-1), "TOP"),
                               ("LINEBELOW",      (0,0),(-1,-1), 0.3, C_BORDER),
                           ])))
        story.append(Spacer(1, 6))

    story += [Spacer(1, 8), EmeraldRule(), Spacer(1, 14)]
    return story


def _section_about(domain, model, S):
    now = datetime.now().strftime("%B %d, %Y at %H:%M")
    data = [
        ["Generated",  now],
        ["Domain",     domain],
        ["Engine",     "CapitalAI-Audit-Crawler v1.0"],
        ["Crawler",    "Crawl4AI (Playwright-based, JS rendering)"],
        ["AI Model",   f"Ollama {model} — 100% local inference"],
        ["Privacy",    "No client data left your machine. Zero cloud APIs."],
        ["Review",     "E-E-A-T Guardian sign-off required before delivery"],
    ]

    story = [
        SectionChip("6", "About This Report"),
        Spacer(1, 10),
    ]

    tdata = [[Paragraph(k, ParagraphStyle("ak", fontName="Helvetica-Bold", fontSize=8,
                                           textColor=C_EMERALD, leading=12)),
              Paragraph(v, ParagraphStyle("av", fontName="Helvetica", fontSize=8,
                                           textColor=C_GREY, leading=12))]
             for k, v in data]
    story.append(_dark_table(tdata, [42*mm, CONTENT_W - 42*mm], header=False, stripe=True))
    story.append(Spacer(1, 14))

    # Final gate notice
    gate_data = [[
        Paragraph("FINAL REVIEW REQUIRED", ParagraphStyle(
            "fg_h", fontName="Helvetica-Bold", fontSize=10, textColor=C_GOLD)),
        Paragraph(
            "All AI-generated scores, excerpts, and recommendations require human verification. "
            "If any finding seems incorrect, escalate immediately. Never deliver unchecked.",
            ParagraphStyle("fg_b", fontName="Helvetica", fontSize=8,
                           textColor=C_GREY, leading=13)),
    ]]
    story.append(Table(gate_data, colWidths=[48*mm, CONTENT_W - 48*mm],
                       style=TableStyle([
                           ("BACKGROUND",    (0,0),(-1,-1), HexColor("#1a1200")),
                           ("LINEBEFORE",    (0,0),(0,-1),  3, C_GOLD),
                           ("LINEAFTER",     (-1,0),(-1,-1), 0.8, C_GOLD),
                           ("LINETOP",       (0,0),(-1,0),  0.8, C_GOLD),
                           ("LINEBELOW",     (0,-1),(-1,-1), 0.8, C_GOLD),
                           ("TOPPADDING",    (0,0),(-1,-1), 10),
                           ("BOTTOMPADDING", (0,0),(-1,-1), 10),
                           ("LEFTPADDING",   (0,0),(-1,-1), 10),
                           ("RIGHTPADDING",  (0,0),(-1,-1), 10),
                           ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                       ])))
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "CapitalAI.ca — Ottawa's Self-Hosted AI SEO Agency",
        ParagraphStyle("footer", fontName="Helvetica-Bold", fontSize=9,
                       textColor=C_EMERALD, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "Privacy-first. Results-focused. No black boxes.",
        ParagraphStyle("tagline", fontName="Helvetica", fontSize=8,
                       textColor=C_GREY, alignment=TA_CENTER)
    ))
    return story


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def write_pdf_report(
    domain: str,
    client_data: dict,
    competitor_data: dict,
    gap_results: dict,
    eeat_scores: dict,
    technical: dict,
    model: str = "llama3.1:8b",
    output_dir: str = "reports",
) -> str:
    """
    Generate a premium branded PDF audit report.
    Returns the path to the written PDF file.
    """
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_domain = domain.replace(".", "_").replace("/", "_")
    filepath    = Path(output_dir) / f"{safe_domain}_{timestamp}_audit.pdf"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    S           = _build_styles()
    agg         = eeat_scores.get("site_aggregate", {})
    overall     = agg.get("overall_score", "N/A")
    date_str    = datetime.now().strftime("%B %d, %Y")

    # ── Doc template with running header/footer ──
    class _AuditDoc(BaseDocTemplate):
        def __init__(self, filename, domain, **kwargs):
            super().__init__(filename, **kwargs)
            self.domain = domain

    doc = _AuditDoc(
        str(filepath),
        domain=domain,
        pagesize=A4,
        topMargin=22*mm,
        bottomMargin=18*mm,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        title=f"SEO Audit — {domain}",
        author="CapitalAI.ca",
        subject="SEO Audit Report",
    )

    # Cover page: full bleed, no margins
    cover_frame   = Frame(0, 0, PAGE_W, PAGE_H, leftPadding=0, rightPadding=0,
                          topPadding=0, bottomPadding=0)
    content_frame = Frame(MARGIN, 18*mm, CONTENT_W, PAGE_H - 40*mm,
                          leftPadding=0, rightPadding=0,
                          topPadding=0, bottomPadding=0)

    doc.addPageTemplates([
        PageTemplate(id="cover",   frames=[cover_frame]),
        PageTemplate(id="content", frames=[content_frame], onPage=_on_page),
    ])

    # ── Build story ──
    story = []
    story += _cover(domain, date_str,
                    len(client_data), len(competitor_data), overall, S)

    # Switch to content template after cover
    from reportlab.platypus import NextPageTemplate
    story.append(NextPageTemplate("content"))
    story.append(PageBreak())

    story += _section_human_gate(S)
    story += _section_toc(S)
    story += _section_exec_summary(domain, client_data, competitor_data,
                                   eeat_scores, technical, S)
    story += _section_eeat(eeat_scores, client_data, S)
    story += _section_gaps(gap_results, competitor_data, S)
    story += _section_technical(technical, client_data, S)
    story += _section_action_plan(eeat_scores, gap_results, technical, S)
    story += _section_about(domain, model, S)

    doc.build(story)
    return str(filepath)
