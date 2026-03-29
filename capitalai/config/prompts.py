GAP_ANALYSIS_PROMPT = """
You are an expert SEO content strategist.

CLIENT TOPICS:
{client_topics}

COMPETITOR TOPICS (from {competitor_count} competitors):
{competitor_topics}

1. List topics competitors cover that the client does NOT (content gaps).
2. List topics only the client covers (unique strengths).
3. Suggest 5 high-priority new content opportunities.
One sentence max per item.

Return ONLY valid JSON, no markdown fences:
{{
  "content_gaps": ["gap1", "gap2"],
  "unique_strengths": ["strength1"],
  "content_opportunities": ["opp1", "opp2", "opp3", "opp4", "opp5"]
}}
"""

EEAT_SCORE_PROMPT = """
You are a Google E-E-A-T auditor. Score this page 0-10 on each dimension.

URL: {url}
TITLE: {title}
META: {meta_description}
HEADINGS: {headings}
CONTENT: {body_excerpt}
SCHEMA: {schema_types}

Return ONLY valid JSON, no markdown fences:
{{
  "experience": 0,
  "expertise": 0,
  "authoritativeness": 0,
  "trustworthiness": 0,
  "overall_score": 0.0,
  "top_issue": "one sentence",
  "quick_fix": "one sentence"
}}
"""

SCHEMA_OPPORTUNITY_PROMPT = """
You are a technical SEO schema expert.

URL: {url}
TITLE: {title}
EXISTING SCHEMA: {existing_schema}
PAGE TYPE: {page_category}

Return ONLY valid JSON, no markdown fences:
{{
  "missing_schema": ["Type1"],
  "priority_schema": "MostImportantType",
  "reason": "one sentence"
}}
"""
