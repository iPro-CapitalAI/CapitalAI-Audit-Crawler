# capitalai/config/prompts.py
# All Ollama prompts for CapitalAI audit layer.
# Keep temperature LOW (0.1-0.2) for all structured output calls.

GAP_ANALYSIS_PROMPT = """\
You are an expert SEO content strategist. Analyze a client website versus competitors.

CLIENT TOPICS (titles + headings):
{client_topics}

COMPETITOR TOPICS (combined from {competitor_count} competitors):
{competitor_topics}

Tasks:
1. List topics competitors cover that the client DOES NOT (content gaps).
2. List topics only the client covers (unique strengths to protect).
3. Suggest 5 high-priority new content opportunities from the gaps.
One sentence max per item.

Return ONLY valid JSON — no markdown fences, no preamble:
{{
  "content_gaps": ["gap1", "gap2"],
  "unique_strengths": ["strength1", "strength2"],
  "content_opportunities": ["opportunity1", "opportunity2", "opportunity3", "opportunity4", "opportunity5"]
}}
"""

EEAT_SCORE_PROMPT = """\
You are a Google E-E-A-T quality auditor. Score this page on each dimension 0–10.

URL: {url}
TITLE: {title}
META DESCRIPTION: {meta_description}
HEADINGS (H1/H2): {headings}
CONTENT EXCERPT (first 800 chars): {body_excerpt}
SCHEMA TYPES DETECTED: {schema_types}

Scoring guide:
- Experience (0-10): First-hand experience signals, case studies, real examples
- Expertise (0-10): Subject-matter depth, accurate technical detail, credentials
- Authoritativeness (0-10): Author bio, citations, external links, brand signals
- Trustworthiness (0-10): Privacy policy, contact info, HTTPS signals, no clickbait

Return ONLY valid JSON — no markdown fences, no preamble:
{{
  "experience": 0,
  "expertise": 0,
  "authoritativeness": 0,
  "trustworthiness": 0,
  "overall_score": 0.0,
  "top_issue": "single most critical weakness in one sentence",
  "quick_fix": "one specific actionable recommendation"
}}
"""

SCHEMA_OPPORTUNITY_PROMPT = """\
You are a technical SEO schema expert. Review this page and identify missing schema.

URL: {url}
TITLE: {title}
DETECTED SCHEMA: {existing_schema}
PAGE TYPE (inferred): {page_category}

Priority schema types: LocalBusiness, FAQ, Article, BreadcrumbList, Service, Review, HowTo, Person

Return ONLY valid JSON:
{{
  "missing_schema": ["Type1", "Type2"],
  "priority_schema": "MostImportantType",
  "reason": "one sentence"
}}
"""
