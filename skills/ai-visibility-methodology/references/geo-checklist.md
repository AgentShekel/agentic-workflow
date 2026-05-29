# GEO Optimization Checklist

Generative Engine Optimization — actionable steps to improve visibility in AI answers.
Based on Stanford research (arxiv.org/abs/2311.09735) and industry best practices.

## Technical Accessibility

- [ ] robots.txt does NOT block AI crawlers:
  - `ChatGPT-User` (OpenAI)
  - `PerplexityBot` (Perplexity)
  - `Google-Extended` (Gemini)
  - `ClaudeBot` (Anthropic)
  - `Bytespider` (DeepSeek via ByteDance)
  - `CCBot` (Common Crawl — used by many LLMs for training)
- [ ] Site loads without JavaScript requirement (SSR/SSG preferred)
- [ ] Clean HTML structure with semantic tags
- [ ] Sitemap.xml is up to date and accessible
- [ ] Page speed is acceptable (Core Web Vitals)
- [ ] Mobile-friendly responsive design

## Content Structure

- [ ] Clear H1 → H2 → H3 hierarchy on every page
- [ ] Each section starts with a direct, concise answer
- [ ] FAQ sections with question-answer format
- [ ] Lists and tables for comparative/structured data
- [ ] "Last updated" dates on key content pages

## Content Authority

- [ ] Original data, statistics, or research published
- [ ] Expert quotes with attribution (name, title, company)
- [ ] Case studies with specific numbers and outcomes
- [ ] Comprehensive "pillar" content on core topics (2000+ words)
- [ ] Content clusters: pillar page + supporting articles with internal links

## Citations & Trust

- [ ] References to authoritative external sources
- [ ] Academic-style citations where relevant
- [ ] Links to official documentation, studies, standards
- [ ] Author bios with expertise credentials
- [ ] "About Us" page with company history, team, credentials

## Structured Data (Schema.org)

- [ ] `LocalBusiness` markup with address, hours, phone
- [ ] `Organization` markup with name, logo, social profiles
- [ ] `FAQPage` markup on FAQ sections
- [ ] `Review` / `AggregateRating` markup
- [ ] `Service` or `Product` markup for offerings
- [ ] `BreadcrumbList` for navigation

## Brand Presence

- [ ] Consistent NAP (Name, Address, Phone) across all platforms
- [ ] Active profiles on major review platforms:
  - Google Business Profile
  - Yandex Maps / Yandex Business
  - 2GIS
  - Industry-specific platforms
- [ ] Wikipedia / Wikidata entry (if notable enough)
- [ ] Press mentions and media coverage
- [ ] Social media presence with regular activity

## Content Freshness

- [ ] Key pages updated at least quarterly
- [ ] Blog/news section with regular posts
- [ ] Seasonal content updated before each season
- [ ] Pricing and offering pages always current
- [ ] Remove or redirect outdated content

## Competitor Analysis

- [ ] Identify which competitors AI platforms mention
- [ ] Analyze their content structure and topics
- [ ] Create comparison content ("X vs Y")
- [ ] Cover topics competitors miss
- [ ] Match or exceed competitor content depth

## Monitoring

- [ ] Monthly AI visibility audit (use ai-visibility-methodology skill)
- [ ] Track Mention Rate and Citation Rate trends
- [ ] Monitor competitor visibility changes
- [ ] Track AI-referred traffic in analytics (Metrika/GA)
- [ ] Alert on visibility drops

## AI Referral Tracking

Yandex Metrika / Google Analytics — filter referrals from:
- `chat.openai.com` / `chatgpt.com`
- `perplexity.ai`
- `gemini.google.com`
- `copilot.microsoft.com`
- `ya.ru` (Yandex Neyro — internal referral)
