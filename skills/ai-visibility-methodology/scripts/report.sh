#!/bin/bash
# Generate AI Visibility Report from check results
# Usage: bash report.sh --results-dir ./results/ --brand "Brand" --url "https://example.com" [--output report.md] [--project slug]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

RESULTS_DIR=""
BRAND=""
SITE_URL=""
OUTPUT=""
FORMAT="md"
PROJECT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --brand) BRAND="$2"; shift 2 ;;
        --url) SITE_URL="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --format) FORMAT="$2"; shift 2 ;;
        --project) PROJECT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Load from project if specified
if [[ -n "$PROJECT" ]]; then
    if [[ -z "$BRAND" ]]; then
        BRAND=$(get_project_field "$PROJECT" "brand-methodology")
    fi
    if [[ -z "$SITE_URL" ]]; then
        SITE_URL=$(get_project_field "$PROJECT" "url")
    fi
fi

if [[ -z "$RESULTS_DIR" || -z "$BRAND" ]]; then
    echo "Usage: bash report.sh --results-dir ./results/ --brand \"Brand\" --url \"https://example.com\""
    echo "       bash report.sh --results-dir ./results/ --project my-brand"
    exit 1
fi

if [[ ! -d "$RESULTS_DIR" ]]; then
    echo "Error: Results directory not found: $RESULTS_DIR"
    exit 1
fi

# Generate full report using Python for reliable JSON parsing and aggregation
python3 << 'PYEOF'
import json, sys, os, re
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse

results_dir = sys.argv[1]
brand = sys.argv[2]
site_url = sys.argv[3]
output_file = sys.argv[4]
project = sys.argv[5]
history_dir = sys.argv[6]

report_date = datetime.now().strftime("%Y-%m-%d")

# Load all result files
platforms = []
total_mentioned = 0
total_links = 0
total_prompts = 0
total_top1 = 0
all_competitors = defaultdict(lambda: {"count": 0, "platforms": set()})
all_sources = defaultdict(lambda: {"count": 0, "platforms": set()})
query_analysis = {"brand-methodology": {"total": 0, "mentioned": 0}, "category": {"total": 0, "mentioned": 0}, "decision": {"total": 0, "mentioned": 0}}

for fname in sorted(os.listdir(results_dir)):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(results_dir, fname)
    try:
        with open(fpath) as f:
            data = json.load(f)
    except:
        continue

    platform = data.get("platform", "unknown")
    metrics = data.get("metrics", {})
    mention_rate = metrics.get("mention_rate", 0)
    citation_rate = metrics.get("citation_rate", 0)
    top1_rate = metrics.get("top1_rate", 0)
    tp = metrics.get("total_prompts", 0)
    mentioned = metrics.get("mentioned", 0)
    links = metrics.get("links_found", 0)

    # Score
    if mention_rate > 70: score = "Excellent"
    elif mention_rate > 40: score = "Good"
    elif mention_rate > 10: score = "Weak"
    else: score = "Invisible"

    platforms.append({
        "name": platform,
        "mention_rate": mention_rate,
        "citation_rate": citation_rate,
        "top1_rate": top1_rate,
        "score": score,
        "total_prompts": tp,
        "mentioned": mentioned,
        "segment": data.get("segment", "")
    })

    total_mentioned += mentioned
    total_links += links
    total_prompts += tp

    # Extract competitors and sources from results
    for r in data.get("results", []):
        # Competitors
        comp_str = r.get("competitors", "")
        if comp_str:
            for name in comp_str.split(", "):
                name = name.strip()
                if name:
                    all_competitors[name]["count"] += 1
                    all_competitors[name]["platforms"].add(platform)

        # Sources from excerpts
        excerpt = r.get("response_excerpt", "")
        urls = re.findall(r'https?://[^\s\)\"<>\]]+', excerpt)
        domains_raw = re.findall(r'(?<!\w)([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|ru|org|net|io|ai|co|dev)[a-zA-Z0-9/.-]*)', excerpt)
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
                if domain:
                    all_sources[domain]["count"] += 1
                    all_sources[domain]["platforms"].add(platform)
            except:
                pass
        for d in domains_raw:
            domain = d.split("/")[0].lower().replace("www.", "")
            if domain and domain not in all_sources:
                all_sources[domain]["count"] += 1
                all_sources[domain]["platforms"].add(platform)

# Overall metrics
overall_mention = (total_mentioned * 100 // total_prompts) if total_prompts > 0 else 0
overall_citation = (total_links * 100 // total_prompts) if total_prompts > 0 else 0

if overall_mention > 70: overall_score = "Excellent"
elif overall_mention > 40: overall_score = "Good"
elif overall_mention > 10: overall_score = "Weak"
else: overall_score = "Invisible"

# Trend data
trend_section = ""
if project and history_dir:
    hist_base = os.path.join(history_dir, project)
    if os.path.isdir(hist_base):
        date_dirs = sorted([d for d in os.listdir(hist_base) if os.path.isdir(os.path.join(hist_base, d))], reverse=True)
        if len(date_dirs) >= 2:
            # Load previous
            prev_dir = os.path.join(hist_base, date_dirs[1])
            prev_mentioned = 0
            prev_links = 0
            prev_prompts = 0
            for pf in os.listdir(prev_dir):
                if not pf.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(prev_dir, pf)) as f:
                        pd = json.load(f)
                    pm = pd.get("metrics", {})
                    prev_mentioned += pm.get("mentioned", 0)
                    prev_links += pm.get("links_found", 0)
                    prev_prompts += pm.get("total_prompts", 0)
                except:
                    pass
            if prev_prompts > 0:
                prev_mr = prev_mentioned * 100 // prev_prompts
                prev_cr = prev_links * 100 // prev_prompts
                delta_mr = overall_mention - prev_mr
                delta_cr = overall_citation - prev_cr
                arrow_mr = "▲" if delta_mr > 0 else ("▼" if delta_mr < 0 else "—")
                arrow_cr = "▲" if delta_cr > 0 else ("▼" if delta_cr < 0 else "—")
                trend_section = f"""
## Trends (vs {date_dirs[1]})

| Metric | Previous | Current | Change |
|--------|----------|---------|--------|
| Mention Rate | {prev_mr}% | {overall_mention}% | {arrow_mr} {delta_mr:+d}% |
| Citation Rate | {prev_cr}% | {overall_citation}% | {arrow_cr} {delta_cr:+d}% |
"""

# Build report
report = f"""# AI Visibility Report: {brand}

**Date:** {report_date}
**Site:** {site_url}
**Platforms checked:** {len(platforms)}
**Total prompts:** {total_prompts}
{f"**Project:** {project}" if project else ""}

---

## Executive Summary

| Metric | Value | Rating |
|--------|-------|--------|
| Overall Mention Rate | {overall_mention}% | {overall_score} |
| Overall Citation Rate | {overall_citation}% | — |
| Platforms checked | {len(platforms)} | — |

## Platform Breakdown

| Platform | Mention Rate | Citation Rate | Top-1 Rate | Score |{" Segment |" if any(p["segment"] for p in platforms) else ""}
|----------|-------------|---------------|------------|-------|{" --------|" if any(p["segment"] for p in platforms) else ""}
"""

for p in platforms:
    seg_col = f" {p['segment']} |" if any(pp["segment"] for pp in platforms) else ""
    report += f"| {p['name']} | {p['mention_rate']}% | {p['citation_rate']}% | {p['top1_rate']}% | {p['score']} |{seg_col}\n"

# Competitor map
if all_competitors:
    report += "\n## Competitor Map\n\n"
    report += f"Brands that AI platforms recommend alongside or instead of {brand}:\n\n"
    report += "| Competitor | Mentions | Platforms |\n"
    report += "|-----------|----------|----------|\n"
    for name, info in sorted(all_competitors.items(), key=lambda x: -x[1]["count"])[:15]:
        plats = ", ".join(sorted(info["platforms"]))
        report += f"| {name} | {info['count']} | {plats} |\n"

# Source analysis
if all_sources:
    report += "\n## Source Analysis\n\n"
    report += "Domains that AI platforms cite in their responses:\n\n"
    report += "| Domain | Citations | Platforms |\n"
    report += "|--------|----------|----------|\n"
    # Filter out own domain
    own_domain = site_url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/") if site_url else ""
    for domain, info in sorted(all_sources.items(), key=lambda x: -x[1]["count"])[:20]:
        is_own = " ★" if own_domain and own_domain in domain else ""
        plats = ", ".join(sorted(info["platforms"]))
        report += f"| {domain}{is_own} | {info['count']} | {plats} |\n"
    if own_domain:
        report += f"\n★ = your domain ({own_domain})\n"

# Trends
if trend_section:
    report += trend_section

# Recommendations
report += f"""
## Recommendations

### If score is "Invisible" or "Weak":
1. Create comprehensive, authoritative content about your niche + location
2. Get listed on major review platforms (Google Maps, 2GIS, Yandex Maps)
3. Publish original data, statistics, case studies
4. Add Schema.org structured data (LocalBusiness, SportsActivityLocation)
5. Ensure AI crawlers are not blocked in robots.txt

### If score is "Good":
1. Strengthen content where you're NOT mentioned (gap analysis)
2. Create comparison content ("X vs Y in {{Location}}")
3. Build topical authority with content clusters
4. Monitor monthly for trend changes

### If score is "Excellent":
1. Maintain content freshness (update dates, new data)
2. Expand to new query types and topics
3. Monitor competitor movements
4. Track AI referral traffic in analytics

## Next Steps

- Re-run this audit in 30 days to track progress
- Cross-reference with Yandex Search positions (yandex-search skill)
- Check AI-referred traffic in Yandex Metrika (yandex-metrika skill)
- Apply GEO optimization checklist (references/geo-checklist.md)
{f"- Run trend analysis: `bash trends.sh --project {project}`" if project else ""}

---
*Generated by ai-visibility-methodology skill*
"""

if output_file:
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report saved to: {output_file}")
else:
    print(report)
PYEOF
-- "$RESULTS_DIR" "$BRAND" "$SITE_URL" "$OUTPUT" "$PROJECT" "$HISTORY_DIR"
