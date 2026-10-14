#!/usr/bin/env python3
"""
Semantic Drift Analyzer — Yandex Edition
Analyzes topical drift of website pages using Yandex Webmaster + Metrika data.

Usage:
  python analyze.py --queries queries.csv --output report.html
  python analyze.py --queries queries.csv --pages pages.json --output report.html
  python analyze.py --queries queries.csv --mode embeddings
"""

import argparse
import json
import csv
import sys
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler


def parse_args():
    p = argparse.ArgumentParser(description="Semantic Drift Analyzer")
    p.add_argument("--queries", required=True, help="CSV with search queries from Webmaster")
    p.add_argument("--pages", help="JSON with page metrics from Metrika")
    p.add_argument("--output", default="drift_report.html", help="Output HTML report")
    p.add_argument("--mode", default="query", choices=["query", "embeddings"])
    p.add_argument("--model", default="all-MiniLM-L6-v2",
                   help="sentence-transformers model for embeddings mode")
    p.add_argument("--alpha", type=float, default=0.6, help="Content weight")
    p.add_argument("--beta", type=float, default=0.3, help="Inlinks weight")
    p.add_argument("--gamma", type=float, default=0.1, help="Clicks weight")
    return p.parse_args()


def load_queries_csv(path):
    """Load Webmaster search queries CSV.
    Expected columns: query, url, clicks, impressions, position (or similar).
    Returns dict: {url: [list of (query, clicks, impressions)]}
    """
    page_queries = defaultdict(list)

    with open(path, "r", encoding="utf-8-sig") as f:
        # Try to detect delimiter
        sample = f.read(2048)
        f.seek(0)

        delimiter = ";"
        if sample.count(",") > sample.count(";"):
            delimiter = ","
        if sample.count("\t") > sample.count(delimiter):
            delimiter = "\t"

        reader = csv.DictReader(f, delimiter=delimiter)
        headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []

        # Map columns flexibly
        url_col = next((h for h in reader.fieldnames if h.strip().lower() in
                        ["url", "page", "address", "страница"]), None)
        query_col = next((h for h in reader.fieldnames if h.strip().lower() in
                          ["query", "keyword", "запрос", "phrase"]), None)
        clicks_col = next((h for h in reader.fieldnames if h.strip().lower() in
                           ["clicks", "клики"]), None)
        impressions_col = next((h for h in reader.fieldnames if h.strip().lower() in
                                ["impressions", "показы", "shows"]), None)

        if not query_col:
            print(f"Error: No query column found. Headers: {reader.fieldnames}")
            sys.exit(1)

        for row in reader:
            query = row.get(query_col, "").strip()
            url = row.get(url_col, "unknown").strip() if url_col else "unknown"
            clicks = float(row.get(clicks_col, 0) or 0) if clicks_col else 0
            impressions = float(row.get(impressions_col, 0) or 0) if impressions_col else 0

            if query:
                page_queries[url].append({
                    "query": query,
                    "clicks": clicks,
                    "impressions": impressions
                })

    return page_queries


def load_metrika_json(path):
    """Load Metrika pages data.
    Returns dict: {url: {pageviews, users, ...}}
    """
    page_metrics = {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle various Metrika output formats
    if isinstance(data, list):
        for item in data:
            url = item.get("url", item.get("page", ""))
            if url:
                page_metrics[url] = {
                    "pageviews": item.get("pageviews", 0),
                    "users": item.get("users", 0),
                    "bounce_rate": item.get("bounce_rate", 0),
                    "avg_duration": item.get("avg_duration", 0),
                }
    elif isinstance(data, dict) and "data" in data:
        for item in data["data"]:
            dims = item.get("dimensions", [])
            metrics = item.get("metrics", [])
            if dims:
                url = dims[0].get("name", "")
                if url:
                    page_metrics[url] = {
                        "pageviews": metrics[0] if len(metrics) > 0 else 0,
                        "users": metrics[1] if len(metrics) > 1 else 0,
                    }

    return page_metrics


def build_tfidf_vectors(page_queries):
    """Build TF-IDF vectors from search queries associated with each page."""
    urls = list(page_queries.keys())

    # Combine all queries per page into a "document", weighted by clicks
    documents = []
    for url in urls:
        queries = page_queries[url]
        # Repeat query proportional to clicks for weighting
        doc_parts = []
        for q in queries:
            repeat = max(1, int(q["clicks"]))
            repeat = min(repeat, 50)  # cap to avoid memory issues
            doc_parts.extend([q["query"]] * repeat)
        documents.append(" ".join(doc_parts))

    # TF-IDF vectorization
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.95,
        sublinear_tf=True,
    )

    tfidf_matrix = vectorizer.fit_transform(documents)

    return urls, tfidf_matrix.toarray(), vectorizer


def build_local_embeddings(page_queries, model_name="all-MiniLM-L6-v2"):
    """Build embeddings locally using sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("Error: sentence-transformers required. Run: pip install sentence-transformers")
        sys.exit(1)

    print(f"  Loading model: {model_name}...")
    model = SentenceTransformer(model_name)
    urls = list(page_queries.keys())

    # Build text for each page from its queries
    texts = []
    for url in urls:
        queries = page_queries[url]
        sorted_q = sorted(queries, key=lambda x: x["clicks"], reverse=True)[:20]
        text = "; ".join(q["query"] for q in sorted_q)
        texts.append(text)

    print(f"  Encoding {len(texts)} documents...")
    embeddings = model.encode(texts, show_progress_bar=len(texts) > 50, batch_size=64)

    return urls, np.array(embeddings)


def compute_centroid(embeddings, inlinks, clicks, alpha=0.6, beta=0.3, gamma=0.1):
    """Compute weighted semantic centroid."""
    inlinks_norm = inlinks / max(inlinks.max(), 1)
    clicks_norm = clicks / max(clicks.max(), 1)

    weights = alpha + beta * inlinks_norm + gamma * clicks_norm

    centroid = np.average(embeddings, axis=0, weights=weights)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    return centroid


def compute_distances(embeddings, centroid):
    """Compute cosine distance from centroid for each page."""
    sims = cosine_similarity(embeddings, centroid.reshape(1, -1)).flatten()
    distances = 1 - sims
    return sims, distances


def compute_sdi(distances, inlinks):
    """Structural Drift Index = internal authority × semantic distance."""
    inlinks_norm = inlinks / max(inlinks.max(), 1)
    sdi = inlinks_norm * distances
    return sdi


def classify_navboost(internal_authority, distances):
    """Classify pages into NavBoost categories."""
    ia_p25 = np.percentile(internal_authority, 25)
    ia_p75 = np.percentile(internal_authority, 75)
    dist_p25 = np.percentile(distances, 25)
    dist_p75 = np.percentile(distances, 75)

    categories = []
    for ia, dist in zip(internal_authority, distances):
        if ia >= ia_p75 and dist >= dist_p75:
            categories.append("Misaligned Core")
        elif ia <= ia_p25 and dist <= dist_p25:
            categories.append("Underlinked Core")
        elif ia <= ia_p25 and dist >= dist_p75:
            categories.append("Junk Drift")
        else:
            categories.append("Healthy Core")

    return categories


def compute_kpis(similarities, distances, ndi):
    """Compute top-level KPIs."""
    return {
        "topical_cohesion": round(float(np.mean(similarities)), 3),
        "focus_drift_ratio": round(float(np.mean(distances <= np.median(distances))), 3),
        "avg_ndi": round(float(np.mean(ndi)), 3),
    }


def scale_minmax(arr):
    """Min-max scale an array to [0, 1]."""
    arr = np.array(arr, dtype=float)
    if arr.max() == arr.min():
        return np.zeros_like(arr)
    return (arr - arr.min()) / (arr.max() - arr.min())


def generate_html_report(pages_data, kpis, output_path):
    """Generate standalone HTML report with Chart.js radial visualization."""

    # Prepare data for Chart.js
    chart_data = []
    for p in pages_data:
        chart_data.append({
            "x": float(p["x_radial"]),
            "y": float(p["y_radial"]),
            "r": max(3, min(30, 3 + p["clicks_norm"] * 27)),
            "url": p["url"],
            "sdi": round(p["sdi"], 3),
            "distance": round(p["distance"], 3),
            "similarity": round(p["similarity"], 3),
            "clicks": int(p["clicks"]),
            "inlinks": int(p["inlinks"]),
            "category": p["category"],
        })

    # Color mapping for categories
    category_colors = {
        "Healthy Core": "rgba(46, 204, 113, 0.7)",
        "Misaligned Core": "rgba(231, 76, 60, 0.7)",
        "Underlinked Core": "rgba(52, 152, 219, 0.7)",
        "Junk Drift": "rgba(149, 165, 166, 0.5)",
    }

    # Category stats
    category_counts = defaultdict(int)
    category_pages = defaultdict(list)
    for p in pages_data:
        category_counts[p["category"]] += 1
        category_pages[p["category"]].append(p)

    # Top drifters (highest SDI)
    top_drifters = sorted(pages_data, key=lambda x: x["sdi"], reverse=True)[:10]

    # Hidden gems (underlinked core, sorted by clicks desc)
    hidden_gems = sorted(
        [p for p in pages_data if p["category"] == "Underlinked Core"],
        key=lambda x: x["clicks"], reverse=True
    )[:10]

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Semantic Drift Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin-bottom: 8px; color: #fff; }}
h2 {{ font-size: 20px; margin: 32px 0 16px; color: #fff; border-bottom: 1px solid #2a2d35; padding-bottom: 8px; }}
h3 {{ font-size: 16px; margin: 16px 0 8px; color: #ccc; }}
.subtitle {{ color: #888; margin-bottom: 24px; }}

/* KPI Cards */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.kpi-card {{ background: #1a1d27; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2d35; }}
.kpi-value {{ font-size: 36px; font-weight: 700; color: #fff; }}
.kpi-label {{ font-size: 13px; color: #888; margin-top: 4px; }}
.kpi-good {{ color: #2ecc71; }}
.kpi-warn {{ color: #f39c12; }}
.kpi-bad {{ color: #e74c3c; }}

/* Category badges */
.cat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.cat-card {{ background: #1a1d27; border-radius: 8px; padding: 16px; border-left: 4px solid; }}
.cat-card.healthy {{ border-color: #2ecc71; }}
.cat-card.misaligned {{ border-color: #e74c3c; }}
.cat-card.underlinked {{ border-color: #3498db; }}
.cat-card.junk {{ border-color: #95a5a6; }}
.cat-count {{ font-size: 28px; font-weight: 700; color: #fff; }}
.cat-label {{ font-size: 12px; color: #888; }}

/* Chart */
.chart-container {{ background: #1a1d27; border-radius: 12px; padding: 24px; margin-bottom: 32px; border: 1px solid #2a2d35; position: relative; }}
.chart-wrap {{ width: 100%; max-width: 800px; margin: 0 auto; aspect-ratio: 1; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
th {{ text-align: left; padding: 10px 12px; background: #1a1d27; color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #2a2d35; }}
td {{ padding: 10px 12px; border-bottom: 1px solid #1a1d27; font-size: 13px; }}
tr:hover td {{ background: #1a1d27; }}
.url-cell {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3498db; }}
.sdi-high {{ color: #e74c3c; font-weight: 600; }}
.sdi-med {{ color: #f39c12; }}
.sdi-low {{ color: #2ecc71; }}

/* Tooltip */
#tooltip {{ position: absolute; background: #2a2d35; color: #fff; padding: 12px; border-radius: 8px; font-size: 12px; pointer-events: none; display: none; z-index: 100; max-width: 350px; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
#tooltip .tip-url {{ color: #3498db; font-weight: 600; word-break: break-all; margin-bottom: 6px; }}
#tooltip .tip-row {{ display: flex; justify-content: space-between; gap: 16px; margin: 2px 0; }}
#tooltip .tip-label {{ color: #888; }}
</style>
</head>
<body>
<div class="container">

<h1>Semantic Drift Report</h1>
<p class="subtitle">Analyzed {len(pages_data)} pages</p>

<!-- KPIs -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-value {'kpi-good' if kpis['topical_cohesion'] >= 0.7 else 'kpi-warn' if kpis['topical_cohesion'] >= 0.5 else 'kpi-bad'}">{kpis['topical_cohesion']}</div>
    <div class="kpi-label">Topical Cohesion</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value {'kpi-good' if kpis['focus_drift_ratio'] >= 0.6 else 'kpi-warn' if kpis['focus_drift_ratio'] >= 0.4 else 'kpi-bad'}">{kpis['focus_drift_ratio']}</div>
    <div class="kpi-label">Focus-Drift Ratio</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{kpis['avg_ndi']}</div>
    <div class="kpi-label">Average NDI</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{len(pages_data)}</div>
    <div class="kpi-label">Pages Analyzed</div>
  </div>
</div>

<!-- Categories -->
<h2>NavBoost Categories</h2>
<div class="cat-grid">
  <div class="cat-card healthy">
    <div class="cat-count">{category_counts.get('Healthy Core', 0)}</div>
    <div class="cat-label">Healthy Core</div>
  </div>
  <div class="cat-card misaligned">
    <div class="cat-count">{category_counts.get('Misaligned Core', 0)}</div>
    <div class="cat-label">Misaligned Core</div>
  </div>
  <div class="cat-card underlinked">
    <div class="cat-count">{category_counts.get('Underlinked Core', 0)}</div>
    <div class="cat-label">Underlinked Core</div>
  </div>
  <div class="cat-card junk">
    <div class="cat-count">{category_counts.get('Junk Drift', 0)}</div>
    <div class="cat-label">Junk Drift</div>
  </div>
</div>

<!-- Radial Map -->
<h2>Radial Drift Map</h2>
<div class="chart-container">
  <div class="chart-wrap">
    <canvas id="driftChart"></canvas>
  </div>
  <div id="tooltip"></div>
</div>

<!-- Top Drifters -->
<h2>Top Drifters (highest SDI — fix first)</h2>
<table>
<thead><tr><th>#</th><th>URL</th><th>SDI</th><th>Distance</th><th>Clicks</th><th>Inlinks</th><th>Category</th></tr></thead>
<tbody>
{"".join(f'''<tr>
<td>{i+1}</td>
<td class="url-cell" title="{p['url']}">{p['url']}</td>
<td class="{'sdi-high' if p['sdi'] > 0.5 else 'sdi-med' if p['sdi'] > 0.2 else 'sdi-low'}">{p['sdi']:.3f}</td>
<td>{p['distance']:.3f}</td>
<td>{int(p['clicks'])}</td>
<td>{int(p['inlinks'])}</td>
<td>{p['category']}</td>
</tr>''' for i, p in enumerate(top_drifters))}
</tbody>
</table>

<!-- Hidden Gems -->
<h2>Hidden Gems (underlinked but on-topic)</h2>
<table>
<thead><tr><th>#</th><th>URL</th><th>Similarity</th><th>Clicks</th><th>Inlinks</th></tr></thead>
<tbody>
{"".join(f'''<tr>
<td>{i+1}</td>
<td class="url-cell" title="{p['url']}">{p['url']}</td>
<td class="sdi-low">{p['similarity']:.3f}</td>
<td>{int(p['clicks'])}</td>
<td>{int(p['inlinks'])}</td>
</tr>''' for i, p in enumerate(hidden_gems)) if hidden_gems else '<tr><td colspan="5" style="color:#888">No underlinked core pages found</td></tr>'}
</tbody>
</table>

</div>

<script>
const data = {json.dumps(chart_data)};
const categoryColors = {json.dumps(category_colors)};

// Draw radial chart
const ctx = document.getElementById('driftChart').getContext('2d');

// Draw orbit circles
function drawOrbits(chart) {{
    const {{ ctx, chartArea: {{ left, right, top, bottom }} }} = chart;
    const cx = (left + right) / 2;
    const cy = (top + bottom) / 2;
    const maxR = Math.min(right - left, bottom - top) / 2;

    ctx.save();
    const orbits = [0.25, 0.5, 0.75, 1.0];
    const labels = ['Core', 'Focus', 'Expansion', 'Peripheral'];

    orbits.forEach((r, i) => {{
        ctx.beginPath();
        ctx.arc(cx, cy, maxR * r, 0, 2 * Math.PI);
        ctx.strokeStyle = 'rgba(255,255,255,0.1)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '11px sans-serif';
        ctx.fillText(labels[i], cx + maxR * r * 0.7 + 4, cy - 4);
    }});
    ctx.restore();
}}

const orbitPlugin = {{
    id: 'orbits',
    beforeDraw: drawOrbits
}};

const chart = new Chart(ctx, {{
    type: 'bubble',
    plugins: [orbitPlugin],
    data: {{
        datasets: [
            ...['Healthy Core', 'Misaligned Core', 'Underlinked Core', 'Junk Drift'].map(cat => ({{
                label: cat,
                data: data.filter(d => d.category === cat).map(d => ({{
                    x: d.x,
                    y: d.y,
                    r: d.r,
                    url: d.url,
                    sdi: d.sdi,
                    distance: d.distance,
                    clicks: d.clicks,
                    inlinks: d.inlinks,
                    category: d.category,
                }})),
                backgroundColor: categoryColors[cat],
                borderColor: categoryColors[cat].replace('0.7', '1').replace('0.5', '0.8'),
                borderWidth: 1,
            }}))
        ]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: true,
        scales: {{
            x: {{
                min: -1.3, max: 1.3,
                display: false,
            }},
            y: {{
                min: -1.3, max: 1.3,
                display: false,
            }}
        }},
        plugins: {{
            legend: {{
                labels: {{ color: '#ccc', padding: 16 }}
            }},
            tooltip: {{
                callbacks: {{
                    label: function(ctx) {{
                        const d = ctx.raw;
                        return [
                            d.url,
                            `SDI: ${{d.sdi}} | Distance: ${{d.distance}}`,
                            `Clicks: ${{d.clicks}} | Inlinks: ${{d.inlinks}}`,
                            `Category: ${{d.category}}`
                        ];
                    }}
                }}
            }}
        }}
    }}
}});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report saved to: {output_path}")


def main():
    args = parse_args()

    # 1. Load data
    print("Loading search queries...")
    page_queries = load_queries_csv(args.queries)
    print(f"  Found queries for {len(page_queries)} pages")

    if len(page_queries) < 3:
        print("Error: Need at least 3 pages with queries for analysis")
        sys.exit(1)

    page_metrics = {}
    if args.pages and os.path.exists(args.pages):
        print("Loading Metrika data...")
        page_metrics = load_metrika_json(args.pages)
        print(f"  Found metrics for {len(page_metrics)} pages")

    # 2. Build vectors
    print(f"Building vectors (mode: {args.mode})...")

    if args.mode == "query":
        urls, embeddings, vectorizer = build_tfidf_vectors(page_queries)
    elif args.mode == "embeddings":
        urls, embeddings = build_local_embeddings(page_queries, args.model)

    print(f"  Vector shape: {embeddings.shape}")

    # 3. Gather page-level metrics
    clicks = np.array([
        sum(q["clicks"] for q in page_queries[url])
        for url in urls
    ], dtype=float)

    impressions = np.array([
        sum(q["impressions"] for q in page_queries[url])
        for url in urls
    ], dtype=float)

    # Estimate inlinks from Metrika data or use impressions as proxy
    inlinks = np.array([
        page_metrics.get(url, {}).get("pageviews", impressions[i] / max(1, impressions.max()) * 10)
        for i, url in enumerate(urls)
    ], dtype=float)

    # 4. Compute centroid
    print("Computing semantic centroid...")
    centroid = compute_centroid(embeddings, inlinks, clicks, args.alpha, args.beta, args.gamma)

    # 5. Compute distances and metrics
    similarities, distances = compute_distances(embeddings, centroid)
    sdi = compute_sdi(distances, inlinks)

    # Internal authority (proxy from inlinks)
    internal_authority = scale_minmax(inlinks)

    # NDI (Navigation Drift Index)
    from sklearn.preprocessing import StandardScaler
    ia_z = StandardScaler().fit_transform(internal_authority.reshape(-1, 1)).flatten()
    dist_z = StandardScaler().fit_transform(distances.reshape(-1, 1)).flatten()
    ndi = ia_z * dist_z

    # Categories
    categories = classify_navboost(internal_authority, distances)

    # KPIs
    kpis = compute_kpis(similarities, distances, ndi)
    print(f"  Topical Cohesion: {kpis['topical_cohesion']}")
    print(f"  Focus-Drift Ratio: {kpis['focus_drift_ratio']}")
    print(f"  Average NDI: {kpis['avg_ndi']}")

    # 6. Compute radial layout
    distances_norm = distances / max(distances.max(), 1e-10)
    n = len(urls)

    # Sort by distance for even angular spread
    order = np.argsort(distances_norm)
    thetas = np.zeros(n)
    thetas[order] = np.linspace(0, 2 * np.pi, n, endpoint=False)

    x_radial = distances_norm * np.cos(thetas)
    y_radial = distances_norm * np.sin(thetas)

    clicks_norm = scale_minmax(clicks)

    # 7. Build pages data
    pages_data = []
    for i, url in enumerate(urls):
        pages_data.append({
            "url": url,
            "similarity": float(similarities[i]),
            "distance": float(distances[i]),
            "sdi": float(sdi[i]),
            "ndi": float(ndi[i]),
            "clicks": float(clicks[i]),
            "impressions": float(impressions[i]),
            "inlinks": float(inlinks[i]),
            "internal_authority": float(internal_authority[i]),
            "category": categories[i],
            "x_radial": float(x_radial[i]),
            "y_radial": float(y_radial[i]),
            "clicks_norm": float(clicks_norm[i]),
        })

    # 8. Generate report
    print("Generating HTML report...")
    generate_html_report(pages_data, kpis, args.output)

    # 9. Print summary
    cat_counts = defaultdict(int)
    for cat in categories:
        cat_counts[cat] += 1

    print("\n=== Summary ===")
    print(f"Pages analyzed: {len(urls)}")
    print(f"Healthy Core: {cat_counts.get('Healthy Core', 0)}")
    print(f"Misaligned Core: {cat_counts.get('Misaligned Core', 0)}")
    print(f"Underlinked Core: {cat_counts.get('Underlinked Core', 0)}")
    print(f"Junk Drift: {cat_counts.get('Junk Drift', 0)}")
    print(f"\nReport: {args.output}")


if __name__ == "__main__":
    main()
