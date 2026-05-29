#!/bin/bash
# Trend Comparison — compare current results with previous history
# Usage: bash trends.sh --project "project-slug" [--current results-dir/] [--output trends.json]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_config

PROJECT=""
CURRENT_DIR=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project) PROJECT="$2"; shift 2 ;;
        --current) CURRENT_DIR="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$PROJECT" ]]; then
    echo "Usage: bash trends.sh --project \"project-slug\" [--current results-dir/] [--output trends.json]"
    echo ""
    echo "Compares current audit results with the most recent historical data."
    echo "If --current is not specified, compares the two most recent history entries."
    exit 1
fi

python3 << 'PYEOF'
import json, sys, os, glob
from datetime import datetime

project = sys.argv[1] if len(sys.argv) > 1 else ""
current_dir = sys.argv[2] if len(sys.argv) > 2 else ""
output_file = sys.argv[3] if len(sys.argv) > 3 else ""
history_base = sys.argv[4] if len(sys.argv) > 4 else ""

def load_results_from_dir(results_dir):
    """Load and aggregate metrics from a results directory."""
    platforms = {}
    total_mentioned = 0
    total_links = 0
    total_prompts = 0

    if not os.path.isdir(results_dir):
        return None

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
        platforms[platform] = {
            "mention_rate": metrics.get("mention_rate", 0),
            "citation_rate": metrics.get("citation_rate", 0),
            "total_prompts": metrics.get("total_prompts", 0),
            "mentioned": metrics.get("mentioned", 0),
            "links_found": metrics.get("links_found", 0)
        }
        total_mentioned += metrics.get("mentioned", 0)
        total_links += metrics.get("links_found", 0)
        total_prompts += metrics.get("total_prompts", 0)

    if not platforms:
        return None

    overall_mention = (total_mentioned * 100 // total_prompts) if total_prompts > 0 else 0
    overall_citation = (total_links * 100 // total_prompts) if total_prompts > 0 else 0

    return {
        "platforms": platforms,
        "overall": {
            "mention_rate": overall_mention,
            "citation_rate": overall_citation,
            "total_prompts": total_prompts
        }
    }

def load_results_from_history(history_dir):
    """Load results from a history date directory (may have multiple files)."""
    if not os.path.isdir(history_dir):
        return None
    # History files are individual platform checks
    return load_results_from_dir(history_dir)

# Find history directories
hist_base = os.path.join(history_base, project)
if not os.path.isdir(hist_base):
    print(f"No history found for project: {project}")
    sys.exit(1)

date_dirs = sorted([d for d in os.listdir(hist_base) if os.path.isdir(os.path.join(hist_base, d))], reverse=True)

if not date_dirs:
    print(f"No history entries for project: {project}")
    sys.exit(1)

# Load current data
current_data = None
current_date = "current"
if current_dir:
    current_data = load_results_from_dir(current_dir)
    current_date = datetime.utcnow().strftime("%Y-%m-%d")
else:
    # Use latest history as current
    current_data = load_results_from_history(os.path.join(hist_base, date_dirs[0]))
    current_date = date_dirs[0]
    date_dirs = date_dirs[1:]  # Remove from comparison pool

# Load previous data
previous_data = None
previous_date = None
for dd in date_dirs:
    prev = load_results_from_history(os.path.join(hist_base, dd))
    if prev:
        previous_data = prev
        previous_date = dd
        break

if not current_data:
    print("Error: Could not load current results")
    sys.exit(1)

if not previous_data:
    print(f"Only one data point found ({current_date}). Need at least 2 audits for trend comparison.")
    # Still output current data as baseline
    trend = {
        "project": project,
        "current_date": current_date,
        "previous_date": None,
        "has_comparison": False,
        "current": current_data,
        "previous": None,
        "trends": None
    }
else:
    # Calculate trends
    trends = {
        "overall": {
            "mention_rate": {
                "current": current_data["overall"]["mention_rate"],
                "previous": previous_data["overall"]["mention_rate"],
                "delta": current_data["overall"]["mention_rate"] - previous_data["overall"]["mention_rate"],
                "direction": "up" if current_data["overall"]["mention_rate"] > previous_data["overall"]["mention_rate"] else ("down" if current_data["overall"]["mention_rate"] < previous_data["overall"]["mention_rate"] else "stable")
            },
            "citation_rate": {
                "current": current_data["overall"]["citation_rate"],
                "previous": previous_data["overall"]["citation_rate"],
                "delta": current_data["overall"]["citation_rate"] - previous_data["overall"]["citation_rate"],
                "direction": "up" if current_data["overall"]["citation_rate"] > previous_data["overall"]["citation_rate"] else ("down" if current_data["overall"]["citation_rate"] < previous_data["overall"]["citation_rate"] else "stable")
            }
        },
        "by_platform": {}
    }

    all_platforms = set(list(current_data["platforms"].keys()) + list(previous_data["platforms"].keys()))
    for p in sorted(all_platforms):
        cur = current_data["platforms"].get(p, {})
        prev = previous_data["platforms"].get(p, {})
        cur_mr = cur.get("mention_rate", 0)
        prev_mr = prev.get("mention_rate", 0)
        cur_cr = cur.get("citation_rate", 0)
        prev_cr = prev.get("citation_rate", 0)

        trends["by_platform"][p] = {
            "mention_rate": {"current": cur_mr, "previous": prev_mr, "delta": cur_mr - prev_mr},
            "citation_rate": {"current": cur_cr, "previous": prev_cr, "delta": cur_cr - prev_cr},
            "status": "new" if p not in previous_data["platforms"] else ("removed" if p not in current_data["platforms"] else "tracked")
        }

    trend = {
        "project": project,
        "current_date": current_date,
        "previous_date": previous_date,
        "has_comparison": True,
        "current": current_data,
        "previous": previous_data,
        "trends": trends
    }

result_json = json.dumps(trend, ensure_ascii=False, indent=2)

if output_file:
    with open(output_file, "w") as f:
        f.write(result_json)
    print(f"Trend analysis saved to: {output_file}")
else:
    print(result_json)

# Print summary
print(f"\n=== Trend Summary: {project} ===")
print(f"Current: {current_date} | Previous: {previous_date or 'N/A'}")
if trend.get("has_comparison") and trend.get("trends"):
    t = trend["trends"]["overall"]
    mr = t["mention_rate"]
    cr = t["citation_rate"]
    arrow_mr = "▲" if mr["delta"] > 0 else ("▼" if mr["delta"] < 0 else "—")
    arrow_cr = "▲" if cr["delta"] > 0 else ("▼" if cr["delta"] < 0 else "—")
    print(f"Mention Rate: {mr['current']}% {arrow_mr} ({mr['delta']:+d}% vs previous)")
    print(f"Citation Rate: {cr['current']}% {arrow_cr} ({cr['delta']:+d}% vs previous)")

    print("\nPer platform:")
    for p, pt in trend["trends"]["by_platform"].items():
        pmr = pt["mention_rate"]
        arrow = "▲" if pmr["delta"] > 0 else ("▼" if pmr["delta"] < 0 else "—")
        print(f"  {p}: {pmr['current']}% {arrow} ({pmr['delta']:+d}%)")
else:
    print("First audit — no comparison available yet.")
    print(f"Mention Rate: {current_data['overall']['mention_rate']}%")
    print(f"Citation Rate: {current_data['overall']['citation_rate']}%")
PYEOF
-- "$PROJECT" "$CURRENT_DIR" "$OUTPUT" "$HISTORY_DIR"
