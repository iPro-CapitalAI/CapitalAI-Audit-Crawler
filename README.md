# CapitalAI-Audit-Crawler

**Self-hosted, Ollama-powered SEO audit engine for CapitalAI.ca**

This is the core technical engine behind CapitalAI.ca. It is a heavily upgraded fork of [Crawl4AI](https://github.com/unclecode/crawl4ai) designed specifically to deliver fast, private, high-quality SEO audits for Ottawa and NCR clients.

### What it does
- Crawls a client website + its top 3–5 competitors in a single run
- Extracts clean, structured data (Markdown + JSON)
- Feeds the data directly into our 7-agent crew for:
  - Gap analysis (keywords, thin content, duplicate content)
  - E-E-A-T scoring
  - Competitor benchmarking
  - Professional audit report generation

### Core Philosophy (Never Violate)
- 100% self-hosted and local-first (runs on our 4090 machine)
- Heavy native Ollama integration — zero cloud API costs or data leaks
- Maximum self-dependence and privacy
- Built for Canadian/Ottawa market signals (postal codes, bilingual intent, local entities)
- Full respect for CapitalAI E-E-A-T guardrails and quality standards

### Success Criteria
- Complete a full client + competitor crawl and deliver a useful gap analysis report in under 10 minutes on local hardware
- Output must be clean enough for our Opportunity Scout and E-E-A-T Guardian agents to consume without extra cleaning
- No client data ever leaves our machines

### Current Status
- Forked from Crawl4AI
- Ollama integration in progress
- Competitor mode, gap analysis, n8n webhook trigger, and report generation to be added

This crawler is the foundation that turns the “Free AI Visibility Audit” promise on capitalai.ca into a real, high-value service.

---

**Where to store it:**

1. **Primary location** → Paste the text above into the README.md of your new repo:  
   `iPro-CapitalAI/CapitalAI-Audit-Crawler`

2. **Secondary location** (for our knowledge base) → Also save a copy as  
   `docs/CapitalAI-Audit-Crawler-README.md`  
   inside your main `capital-ai-projects` folder.

Would you like me to also give you a shorter version for the GitHub repo description field (under 350 characters)? Or are you good with this full README?  

Just say the word and we’ll move to the next step of actually forking and setting up the project.