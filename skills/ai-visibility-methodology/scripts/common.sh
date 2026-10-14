#!/bin/bash
# Common functions for AI Visibility checks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/.env"
DATA_DIR="$SCRIPT_DIR/../data"
HISTORY_DIR="$DATA_DIR/history"
PROJECTS_DIR="$DATA_DIR/projects"

load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        set -a
        source "$CONFIG_FILE"
        set +a
    fi
    # Ensure data dirs exist
    mkdir -p "$HISTORY_DIR" "$PROJECTS_DIR"
}

# ========== Project Management ==========

# Initialize or load a project (brand + competitors + segments)
# Usage: init_project "project-slug"
# Creates: data/projects/{slug}/project.json
init_project() {
    local slug="$1"
    local project_dir="$PROJECTS_DIR/$slug"
    mkdir -p "$project_dir"
    if [[ ! -f "$project_dir/project.json" ]]; then
        cat > "$project_dir/project.json" <<'PEOF'
{
  "slug": "",
  "brand-methodology": "",
  "url": "",
  "location": "",
  "niche": "",
  "services": [],
  "competitors": [],
  "segments": [],
  "created_at": "",
  "updated_at": ""
}
PEOF
        # Fill slug and timestamp
        python3 -c "
import json, sys
from datetime import datetime
d = json.load(open('$project_dir/project.json'))
d['slug'] = '$slug'
d['created_at'] = datetime.utcnow().isoformat() + 'Z'
d['updated_at'] = d['created_at']
json.dump(d, open('$project_dir/project.json', 'w'), ensure_ascii=False, indent=2)
" 2>/dev/null
    fi
    echo "$project_dir"
}

# Save project field
# Usage: save_project_field "project-slug" "brand-methodology" "Ботек"
save_project_field() {
    local slug="$1" field="$2" value="$3"
    local pfile="$PROJECTS_DIR/$slug/project.json"
    [[ ! -f "$pfile" ]] && init_project "$slug" > /dev/null
    python3 -c "
import json
from datetime import datetime
d = json.load(open('$pfile'))
d['$field'] = '$value'
d['updated_at'] = datetime.utcnow().isoformat() + 'Z'
json.dump(d, open('$pfile', 'w'), ensure_ascii=False, indent=2)
" 2>/dev/null
}

# Save project array field (competitors, services, segments)
# Usage: save_project_array "project-slug" "competitors" '["A","B","C"]'
save_project_array() {
    local slug="$1" field="$2" json_array="$3"
    local pfile="$PROJECTS_DIR/$slug/project.json"
    [[ ! -f "$pfile" ]] && init_project "$slug" > /dev/null
    python3 -c "
import json
from datetime import datetime
d = json.load(open('$pfile'))
d['$field'] = json.loads('$json_array')
d['updated_at'] = datetime.utcnow().isoformat() + 'Z'
json.dump(d, open('$pfile', 'w'), ensure_ascii=False, indent=2)
" 2>/dev/null
}

# Get project field
# Usage: get_project_field "project-slug" "brand-methodology"
get_project_field() {
    local slug="$1" field="$2"
    local pfile="$PROJECTS_DIR/$slug/project.json"
    [[ ! -f "$pfile" ]] && return 1
    python3 -c "
import json
d = json.load(open('$pfile'))
v = d.get('$field', '')
if isinstance(v, list):
    print(json.dumps(v, ensure_ascii=False))
else:
    print(v)
" 2>/dev/null
}

# List all projects
list_projects() {
    for pdir in "$PROJECTS_DIR"/*/; do
        [[ ! -d "$pdir" ]] && continue
        local pfile="$pdir/project.json"
        [[ ! -f "$pfile" ]] && continue
        python3 -c "
import json
d = json.load(open('$pfile'))
print(f\"{d['slug']}\t{d.get('brand-methodology','')}\t{d.get('url','')}\t{d.get('updated_at','')}\")
" 2>/dev/null
    done
}

# ========== History Management ==========

# Save check results to history
# Usage: save_to_history "project-slug" "results.json"
save_to_history() {
    local slug="$1" results_file="$2"
    local date_str
    date_str=$(date +%Y-%m-%d)
    local time_str
    time_str=$(date +%H%M%S)
    local hist_dir="$HISTORY_DIR/$slug/$date_str"
    mkdir -p "$hist_dir"
    cp "$results_file" "$hist_dir/check-${time_str}.json"
    echo "$hist_dir/check-${time_str}.json"
}

# Get latest history entry for a project
# Usage: get_latest_history "project-slug"
get_latest_history() {
    local slug="$1"
    local hist_base="$HISTORY_DIR/$slug"
    [[ ! -d "$hist_base" ]] && return 1
    # Find latest date dir, then latest file
    local latest_dir
    latest_dir=$(ls -1d "$hist_base"/*/ 2>/dev/null | sort -r | head -1)
    [[ -z "$latest_dir" ]] && return 1
    local latest_file
    latest_file=$(ls -1 "$latest_dir"*.json 2>/dev/null | sort -r | head -1)
    [[ -z "$latest_file" ]] && return 1
    echo "$latest_file"
}

# Get previous history entry (second latest date)
# Usage: get_previous_history "project-slug"
get_previous_history() {
    local slug="$1"
    local hist_base="$HISTORY_DIR/$slug"
    [[ ! -d "$hist_base" ]] && return 1
    local prev_dir
    prev_dir=$(ls -1d "$hist_base"/*/ 2>/dev/null | sort -r | head -2 | tail -1)
    [[ -z "$prev_dir" ]] && return 1
    local prev_file
    prev_file=$(ls -1 "$prev_dir"*.json 2>/dev/null | sort -r | head -1)
    [[ -z "$prev_file" ]] && return 1
    echo "$prev_file"
}

# List history dates for a project
# Usage: list_history_dates "project-slug"
list_history_dates() {
    local slug="$1"
    local hist_base="$HISTORY_DIR/$slug"
    [[ ! -d "$hist_base" ]] && return 1
    ls -1d "$hist_base"/*/ 2>/dev/null | xargs -I{} basename {} | sort -r
}

# ========== Source Extraction ==========

# Extract URLs/domains from LLM response text
# Returns JSON array of unique domains
extract_sources() {
    local text="$1"
    python3 -c "
import re, json, sys
from urllib.parse import urlparse

text = '''$text'''
# Find all URLs
urls = re.findall(r'https?://[^\s\)\"<>\]]+', text)
# Find domain-like patterns (example.com, example.ru)
domains_raw = re.findall(r'(?<!\w)([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|ru|org|net|io|ai|co|dev|pro|info|biz|me)[a-zA-Z0-9/.-]*)', text)

sources = {}
for url in urls:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        if domain:
            sources[domain] = sources.get(domain, 0) + 1
    except:
        pass

for d in domains_raw:
    domain = d.split('/')[0].lower().replace('www.', '')
    if domain and domain not in sources:
        sources[domain] = 1

# Sort by frequency
sorted_sources = sorted(sources.items(), key=lambda x: -x[1])
result = [{'domain': d, 'count': c} for d, c in sorted_sources]
print(json.dumps(result, ensure_ascii=False))
" 2>/dev/null
}

# Check if a brand is mentioned in text (case-insensitive, supports Cyrillic)
check_mention() {
    local text="$1"
    local brand="$2"
    # Check both original and lowercased
    if echo "$text" | grep -qi "$brand"; then
        echo "true"
    else
        echo "false"
    fi
}

# Check if a URL/domain is present in text
check_link() {
    local text="$1"
    local domain="$2"
    # Strip protocol and www
    local clean_domain
    clean_domain=$(echo "$domain" | sed 's|https\?://||; s|^www\.||; s|/$||')
    if echo "$text" | grep -qi "$clean_domain"; then
        echo "true"
    else
        echo "false"
    fi
}

# Simple sentiment analysis based on keyword matching
# Returns: positive, negative, neutral
analyze_sentiment() {
    local text="$1"
    local brand="$2"
    local lower_text
    lower_text=$(echo "$text" | tr '[:upper:]' '[:lower:]')

    local pos_count=0
    local neg_count=0

    # Positive signals (Russian + English)
    for word in "лучш" "рекоменд" "отличн" "популярн" "качеств" "надёжн" "надежн" "удобн" \
                "best" "recommend" "excellent" "popular" "quality" "top" "great" "premier"; do
        if echo "$lower_text" | grep -q "$word"; then
            pos_count=$((pos_count + 1))
        fi
    done

    # Negative signals
    for word in "плох" "недостат" "минус" "проблем" "жалоб" "дорог" "устарел" \
                "poor" "bad" "issue" "problem" "expensive" "outdated" "complaint"; do
        if echo "$lower_text" | grep -q "$word"; then
            neg_count=$((neg_count + 1))
        fi
    done

    if [[ $pos_count -gt $neg_count ]]; then
        echo "positive"
    elif [[ $neg_count -gt $pos_count ]]; then
        echo "negative"
    else
        echo "neutral"
    fi
}

# Find position of brand mention in a list-like response
# Returns position number (1-based) or 0 if not found
find_position() {
    local text="$1"
    local brand="$2"
    local position=0
    local counter=0

    # Split by common list patterns (numbered, bulleted, etc.)
    while IFS= read -r line; do
        if echo "$line" | grep -qE '^[0-9]+[\.\):]|^[-*•]|^\*\*'; then
            counter=$((counter + 1))
            if echo "$line" | grep -qi "$brand"; then
                position=$counter
                break
            fi
        fi
    done <<< "$text"

    echo "$position"
}

# Extract competitor names from response (brands mentioned that aren't ours)
extract_competitors() {
    local text="$1"
    local brand="$2"
    # This is a simplified extractor — works best with list-formatted responses
    local competitors=""
    while IFS= read -r line; do
        if echo "$line" | grep -qE '^[0-9]+[\.\):]|^[-*•]|^\*\*'; then
            if ! echo "$line" | grep -qi "$brand"; then
                # Extract the first bold or quoted text as competitor name
                local name
                name=$(echo "$line" | grep -oP '\*\*([^*]+)\*\*' | head -1 | sed 's/\*\*//g')
                if [[ -z "$name" ]]; then
                    name=$(echo "$line" | grep -oP '«([^»]+)»' | head -1 | sed 's/[«»]//g')
                fi
                if [[ -z "$name" ]]; then
                    # Take first meaningful words after list marker
                    name=$(echo "$line" | sed 's/^[0-9]*[\.\):\-\*•]*//' | sed 's/^[[:space:]]*//' | cut -d' ' -f1-3 | sed 's/[[:space:]]*$//')
                fi
                if [[ -n "$name" ]]; then
                    if [[ -n "$competitors" ]]; then
                        competitors="$competitors, $name"
                    else
                        competitors="$name"
                    fi
                fi
            fi
        fi
    done <<< "$text"
    echo "$competitors"
}

# JSON escape a string
json_escape() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\r'/}"
    str="${str//$'\t'/\\t}"
    echo "$str"
}

# Create result JSON for one prompt check
make_result_json() {
    local prompt="$1"
    local mentioned="$2"
    local link_present="$3"
    local position="$4"
    local sentiment="$5"
    local competitors="$6"
    local excerpt="$7"

    local esc_prompt esc_competitors esc_excerpt
    esc_prompt=$(json_escape "$prompt")
    esc_competitors=$(json_escape "$competitors")
    esc_excerpt=$(json_escape "$excerpt")

    cat <<EOF
    {
      "prompt": "$esc_prompt",
      "mentioned": $mentioned,
      "link_present": $link_present,
      "position": $position,
      "sentiment": "$sentiment",
      "competitors": "$esc_competitors",
      "response_excerpt": "$esc_excerpt"
    }
EOF
}

# Truncate text to N characters for excerpt
truncate_text() {
    local text="$1"
    local max_len="${2:-300}"
    if [[ ${#text} -gt $max_len ]]; then
        echo "${text:0:$max_len}..."
    else
        echo "$text"
    fi
}
