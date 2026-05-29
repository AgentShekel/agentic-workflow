---
name: design-assets-guide
domain: design
description: |
  [METHODOLOGY] AI-generated visual assets pipeline — logo generation
  (55 styles, Gemini AI), corporate identity program (50 deliverables, CIP
  mockups), icon design (15 styles, SVG, Gemini 3.1 Pro), social photos
  (HTML→screenshot, multi-platform). Preloaded by design-visual-designer agent.
argument-hint: "[asset-type] [context]"
license: MIT
metadata:
  author: claudekit
  version: "3.0.0"
---

# Design Assets

AI-generated visual assets: logo, CIP, icons, social photos. Uses Gemini AI for generation.

For UI/component work use `ui-styling-guide`. For banners use `banner-design-guide`. For presentations use `presentation-design`. For design tokens use `design-system-methodology`. For brand identity use `brand-methodology`.

## When to Use

- Logo design and AI generation
- Corporate identity program (CIP) deliverables and mockups
- SVG icon design and generation
- Social photos for Instagram, Facebook, LinkedIn, Twitter, Pinterest, TikTok

## Logo Design

55+ styles, 30 color palettes, 25 industry guides. Gemini models.

### Logo: Generate Design Brief

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/logo/search.py "tech startup modern" --design-brief -p "BrandName"
```

### Logo: Search Styles/Colors/Industries

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/logo/search.py "minimalist clean" --domain style
python3 ~/.claude/skills/design-assets-guide/scripts/logo/search.py "tech professional" --domain color
python3 ~/.claude/skills/design-assets-guide/scripts/logo/search.py "healthcare medical" --domain industry
```

### Logo: Generate with AI

**ALWAYS** generate output logo images with white background.

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/logo/generate.py --brand "TechFlow" --style minimalist --industry tech
python3 ~/.claude/skills/design-assets-guide/scripts/logo/generate.py --prompt "coffee shop vintage badge" --style vintage
```

**IMPORTANT:** When scripts fail, try to fix them directly.

After generation, **ALWAYS** ask user about HTML preview via `AskUserQuestion`. If yes, invoke `ui-ux-methodology` for gallery.

## CIP Design

50+ deliverables, 20 styles, 20 industries. Gemini (Flash/Pro).

### CIP: Generate Brief

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/cip/search.py "tech startup" --cip-brief -b "BrandName"
```

### CIP: Search Domains

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/cip/search.py "business card letterhead" --domain deliverable
python3 ~/.claude/skills/design-assets-guide/scripts/cip/search.py "luxury premium elegant" --domain style
python3 ~/.claude/skills/design-assets-guide/scripts/cip/search.py "hospitality hotel" --domain industry
python3 ~/.claude/skills/design-assets-guide/scripts/cip/search.py "office reception" --domain mockup
```

### CIP: Generate Mockups

```bash
# With logo (RECOMMENDED)
python3 ~/.claude/skills/design-assets-guide/scripts/cip/generate.py --brand "TopGroup" --logo /path/to/logo.png --deliverable "business card" --industry "consulting"

# Full CIP set
python3 ~/.claude/skills/design-assets-guide/scripts/cip/generate.py --brand "TopGroup" --logo /path/to/logo.png --industry "consulting" --set

# Pro model (4K text)
python3 ~/.claude/skills/design-assets-guide/scripts/cip/generate.py --brand "TopGroup" --logo logo.png --deliverable "business card" --model pro

# Without logo
python3 ~/.claude/skills/design-assets-guide/scripts/cip/generate.py --brand "TechFlow" --deliverable "business card" --no-logo-prompt
```

Models: `flash` (default, `gemini-2.5-flash-image`), `pro` (`gemini-3-pro-image-preview`)

### CIP: Render HTML Presentation

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/cip/render-html.py --brand "TopGroup" --industry "consulting" --images /path/to/cip-output
```

**Tip:** If no logo exists, use Logo Design section above first.

## Icon Design

15 styles, 12 categories. Gemini 3.1 Pro Preview generates SVG text output.

### Icon: Generate Single Icon

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/icon/generate.py --prompt "settings gear" --style outlined
python3 ~/.claude/skills/design-assets-guide/scripts/icon/generate.py --prompt "shopping cart" --style filled --color "#6366F1"
python3 ~/.claude/skills/design-assets-guide/scripts/icon/generate.py --name "dashboard" --category navigation --style duotone
```

### Icon: Generate Batch Variations

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/icon/generate.py --prompt "cloud upload" --batch 4 --output-dir ./icons
```

### Icon: Multi-size Export

```bash
python3 ~/.claude/skills/design-assets-guide/scripts/icon/generate.py --prompt "user profile" --sizes "16,24,32,48" --output-dir ./icons
```

### Icon: Top Styles

| Style | Best For |
|-------|----------|
| outlined | UI interfaces, web apps |
| filled | Mobile apps, nav bars |
| duotone | Marketing, landing pages |
| rounded | Friendly apps, health |
| sharp | Tech, fintech, enterprise |
| flat | Material design, Google-style |
| gradient | Modern brands, SaaS |

**Model:** `gemini-3.1-pro-preview` — text-only output (SVG is XML text).

## Social Photos

Multi-platform social image design: HTML/CSS → screenshot export. Uses `ui-ux-methodology`, `brand-methodology`, `design-system-methodology`, `chrome-devtools` skills.

Load `references/social-photos-design.md` for sizes, templates, best practices.

### Social Photos: Workflow

1. **Analyze** — Parse prompt: subject, platforms, style, brand context, content elements
2. **Ideate** — 3-5 concepts, present to user
3. **Design** — Load `brand-methodology` + `design-system-methodology` + `ui-ux-methodology`; HTML per idea × size
4. **Export** — `chrome-devtools` or Playwright screenshot at exact px (2x deviceScaleFactor)
5. **Verify** — Visually inspect exported designs; fix layout/styling issues and re-export

### Social Photos: Key Sizes

| Platform | Size (px) | Platform | Size (px) |
|----------|-----------|----------|-----------|
| IG Post | 1080×1080 | FB Post | 1200×630 |
| IG Story | 1080×1920 | X Post | 1200×675 |
| IG Carousel | 1080×1350 | LinkedIn | 1200×627 |
| YT Thumb | 1280×720 | Pinterest | 1000×1500 |

## References

| Topic | File |
|-------|------|
| Logo Design Guide | `references/logo-design.md` |
| Logo Styles | `references/logo-style-guide.md` |
| Logo Colors | `references/logo-color-psychology.md` |
| Logo Prompts | `references/logo-prompt-engineering.md` |
| CIP Design Guide | `references/cip-design.md` |
| CIP Deliverables | `references/cip-deliverable-guide.md` |
| CIP Styles | `references/cip-style-guide.md` |
| CIP Prompts | `references/cip-prompt-engineering.md` |
| Icon Design Guide | `references/icon-design.md` |
| Social Photos Guide | `references/social-photos-design.md` |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/logo/search.py` | Search logo styles, colors, industries |
| `scripts/logo/generate.py` | Generate logos with Gemini AI |
| `scripts/logo/core.py` | BM25 search engine for logo data |
| `scripts/cip/search.py` | Search CIP deliverables, styles, industries |
| `scripts/cip/generate.py` | Generate CIP mockups with Gemini |
| `scripts/cip/render-html.py` | Render HTML presentation from CIP mockups |
| `scripts/cip/core.py` | BM25 search engine for CIP data |
| `scripts/icon/generate.py` | Generate SVG icons with Gemini 3.1 Pro |

## Setup

```bash
export GEMINI_API_KEY="your-key"  # https://aistudio.google.com/apikey
pip install google-genai pillow
```

## Integration

**Inputs from:** `brand-methodology` (identity), `ui-ux-methodology` (style recommendations)
**Used by:** `banner-design-guide` (logo assets), `design-visual-designer` agent (logo, CIP, icon workflows)
