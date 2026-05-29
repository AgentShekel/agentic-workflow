#!/bin/bash
# Source Analysis — extract and analyze URLs/domains from LLM check results
# Usage: bash sources.sh --results-dir ./results/ --brand "Brand" [--output sources.json]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

RESULTS_DIR=""
BRAND=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --brand) BRAND="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$RESULTS_DIR" ]]; then
    echo "Usage: bash sources.sh --results-dir ./results/ --brand \"Brand\" [--output sources.json]"
    exit 1
fi

if [[ ! -d "$RESULTS_DIR" ]]; then
    echo "Error: Results directory not found: $RESULTS_DIR"
    exit 1
fi

# Aggregate sources from all result files
python3 << 'PYEOF'
import json, sys, os, re
from urllib.parse import urlparse
from collections import defaultdict

results_dir = sys.argv[1] if len(sys.argv) > 1 else ""
brand = sys.argv[2] if len(sys.argv) > 2 else ""
output = sys.argv[3] if len(sys.argv) > 3 else ""

sources_by_platform = {}
all_sources = defaultdict(lambda: {"count": 0, "platforms": set(), "prompts": []})

for fname in os.listdir(results_dir):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(results_dir, fname)
    try:
        with open(fpath) as f:
            data = json.load(f)
    except:
        continue

    platform = data.get("platform", "unknown")
    platform_sources = defaultdict(int)

    for result in data.get("results", []):
        excerpt = result.get("response_excerpt", "")
        prompt = result.get("prompt", "")

        # Extract URLs
        urls = re.findall(r'https?://[^\s\)\"<>\]]+', excerpt)
        # Extract domain-like patterns
        domain_patterns = re.findall(
            r'(?<!\w)([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|ru|org|net|io|ai|co|dev|pro|info|biz|me)[a-zA-Z0-9/.-]*)',
            excerpt
        )

        domains_found = set()
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
                if domain:
                    domains_found.add(domain)
            except:
                pass
        for d in domain_patterns:
            domain = d.split("/")[0].lower().replace("www.", "")
            if domain:
                domains_found.add(domain)

        for domain in domains_found:
            platform_sources[domain] += 1
            all_sources[domain]["count"] += 1
            all_sources[domain]["platforms"].add(platform)
            if prompt not in all_sources[domain]["prompts"]:
                all_sources[domain]["prompts"].append(prompt)

    sources_by_platform[platform] = dict(sorted(platform_sources.items(), key=lambda x: -x[1]))

# Build output
output_data = {
    "brand-methodology": brand,
    "analyzed_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "total_unique_sources": len(all_sources),
    "sources": [],
    "by_platform": {}
}

# Sort by total count
for domain, info in sorted(all_sources.items(), key=lambda x: -x[1]["count"]):
    output_data["sources"].append({
        "domain": domain,
        "total_mentions": info["count"],
        "platforms": sorted(info["platforms"]),
        "prompt_count": len(info["prompts"]),
        "sample_prompts": info["prompts"][:3]
    })

for platform, sources in sources_by_platform.items():
    output_data["by_platform"][platform] = [
        {"domain": d, "count": c} for d, c in list(sources.items())[:20]
    ]

result_json = json.dumps(output_data, ensure_ascii=False, indent=2, default=list)

if output:
    with open(output, "w") as f:
        f.write(result_json)
    print(f"Source analysis saved to: {output}")
    print(f"Total unique sources: {len(all_sources)}")
    for s in output_data["sources"][:10]:
        print(f"  {s['domain']}: {s['total_mentions']} mentions across {len(s['platforms'])} platforms")
else:
    print(result_json)
PYEOF
-- "$RESULTS_DIR" "$BRAND" "$OUTPUT"
