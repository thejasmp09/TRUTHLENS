"""
HTML report generator using Jinja2 templates.
Converts Markdown autopsy reports into standalone HTML pages.
"""

import os
import logging
import re

from jinja2 import Template

import config
import json

logger = logging.getLogger(__name__)

# — Minimal Markdown -> HTML converter (avoids extra dependency) —

def _md_to_html(md: str) -> str:
    """Bare-bones Markdown to HTML. Handles headers, bold, links, lists, blockquotes."""
    lines = md.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Headers
        if stripped.startswith("######"):
            stripped = f"<h6>{stripped[6:].strip()}</h6>"
        elif stripped.startswith("#####"):
            stripped = f"<h5>{stripped[5:].strip()}</h5>"
        elif stripped.startswith("####"):
            stripped = f"<h4>{stripped[4:].strip()}</h4>"
        elif stripped.startswith("###"):
            stripped = f"<h3>{stripped[3:].strip()}</h3>"
        elif stripped.startswith("##"):
            stripped = f"<h2>{stripped[2:].strip()}</h2>"
        elif stripped.startswith("#"):
            stripped = f"<h1>{stripped[1:].strip()}</h1>"
        # Blockquotes
        elif stripped.startswith(">"):
            stripped = f"<blockquote>{stripped[1:].strip()}</blockquote>"
        # Unordered list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            stripped = f"<li>{stripped[2:]}</li>"
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if stripped == "":
                stripped = ""
            else:
                stripped = f"<p>{stripped}</p>"

        # Inline: bold
        stripped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
        # Inline: links
        stripped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', stripped)
        # Inline: code
        stripped = re.sub(r"`([^`]+)`", r"<code>\1</code>", stripped)

        html_lines.append(stripped)

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


# — HTML template —

REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TruthLens - {{ title }}</title>
    <style>
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --muted: #8b949e;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
            --blue: #58a6ff;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.7;
            padding: 2rem;
            max-width: 800px;
            margin: 0 auto;
        }
        header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }
        header h1 { color: var(--blue); font-size: 1.5rem; }
        header .meta { color: var(--muted); font-size: 0.85rem; margin-top: 0.5rem; }
        .verdict-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 1rem;
            font-weight: 600;
            font-size: 0.85rem;
            margin: 0.5rem 0;
        }
        .verdict-confirmed { background: #0d2818; color: var(--green); border: 1px solid var(--green); }
        .verdict-false { background: #2d1215; color: var(--red); border: 1px solid var(--red); }
        .verdict-unverified { background: #2d2200; color: var(--yellow); border: 1px solid var(--yellow); }
        .content { margin-bottom: 2rem; }
        .content h1, .content h2, .content h3 { margin: 1.5rem 0 0.5rem; color: var(--blue); }
        .content h1 { font-size: 1.4rem; }
        .content h2 { font-size: 1.2rem; }
        .content h3 { font-size: 1.05rem; }
        .content p { margin-bottom: 0.75rem; }
        .content blockquote {
            border-left: 3px solid var(--border);
            padding-left: 1rem;
            color: var(--muted);
            margin: 1rem 0;
        }
        .content ul { padding-left: 1.5rem; margin-bottom: 0.75rem; }
        .content li { margin-bottom: 0.25rem; }
        .content a { color: var(--blue); text-decoration: none; }
        .content a:hover { text-decoration: underline; }
        .content code {
            background: var(--surface);
            padding: 0.15rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.9em;
        }
        .content strong { color: #fff; }
        footer {
            border-top: 1px solid var(--border);
            padding-top: 1rem;
            margin-top: 2rem;
            color: var(--muted);
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>TruthLens Autopsy Report</h1>
        <div class="meta">
            Platform: {{ platform }} &middot; Author: @{{ author }} &middot; Analyzed: {{ created_at }}
        </div>
        <div style="margin-top: 0.75rem;">
            <span class="verdict-badge {{ verdict_class }}">{{ overall_verdict }}</span>
            <span style="color: var(--muted); font-size: 0.85rem; margin-left: 0.5rem;">
                Confidence: {{ confidence }}
            </span>
        </div>
    </header>
    {% if key_findings_html %}
    <section style="margin:1rem 0; background:var(--surface); padding:1rem; border:1px solid var(--border); border-radius:0.5rem;">
        <h2 style="color:var(--blue); margin-bottom:0.5rem;">Key Findings</h2>
        {{ key_findings_html | safe }}
    </section>
    {% endif %}
    <div class="content">
        {{ body_html }}
    </div>
    {% if agent_json %}
    <details style="margin-bottom:1rem;">
        <summary style="cursor:pointer; color:var(--blue);">Agent details (JSON)</summary>
        <pre style="background:var(--surface); padding:1rem; color:var(--muted); overflow:auto; max-height:400px;">{{ agent_json }}</pre>
    </details>
    {% endif %}
    <footer>
        Generated by TruthLens &mdash; automated misinformation autopsy.
        This report is machine-generated and should be verified by a human.
    </footer>
</body>
</html>
""")


INDEX_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TruthLens - Reports</title>
    <style>
        :root {
            --bg: #0d1117; --surface: #161b22; --border: #30363d;
            --text: #e6edf3; --muted: #8b949e; --blue: #58a6ff;
            --green: #3fb950; --red: #f85149; --yellow: #d29922;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: var(--bg); color: var(--text); padding: 2rem;
            max-width: 800px; margin: 0 auto;
        }
        h1 { color: var(--blue); margin-bottom: 1.5rem; }
        .report-card {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem;
        }
        .report-card a { color: var(--blue); text-decoration: none; font-weight: 600; }
        .report-card a:hover { text-decoration: underline; }
        .report-card .meta { color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }
        .verdict-confirmed { color: var(--green); }
        .verdict-false { color: var(--red); }
        .verdict-unverified { color: var(--yellow); }
    </style>
</head>
<body>
    <h1>TruthLens Reports</h1>
        <div style="margin: 1.5rem 0 2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
            <div style="background:var(--surface); padding:1rem; border:1px solid var(--border); border-radius:0.5rem;">
                <h3 style="color:var(--blue); margin-bottom:0.5rem;">Verdict Breakdown</h3>
                <canvas id="verdictChart" width="400" height="200"></canvas>
            </div>
            <div style="background:var(--surface); padding:1rem; border:1px solid var(--border); border-radius:0.5rem;">
                <h3 style="color:var(--blue); margin-bottom:0.5rem;">Platform Breakdown</h3>
                <canvas id="platformChart" width="400" height="200"></canvas>
            </div>
        </div>
    {% for r in reports %}
    <div class="report-card">
        <a href="{{ r.filename }}">Report #{{ r.id }}</a>
        <span class="{{ r.verdict_class }}"> - {{ r.overall_verdict }}</span>
        <div class="meta">{{ r.platform }} &middot; {{ r.created_at }}</div>
         {% if r.excerpt_html %}
        <div style="margin-top:0.5rem; color:var(--muted);">{{ r.excerpt_html | safe }}</div>
        {% endif %}
        {% if r.key_findings_html %}
        <div style="margin-top:0.5rem; background:transparent; border-top:1px solid var(--border); padding-top:0.5rem;">
            <strong style="color:var(--blue);">Key Findings:</strong>
            <div style="color:var(--muted); margin-top:0.25rem;">{{ r.key_findings_html | safe }}</div>
        </div>
        {% endif %}
    </div>
    {% endfor %}
    {% if not reports %}
    <p style="color: var(--muted);">No reports yet. TruthLens is watching...</p>
    {% endif %}
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const verdictData = {{ verdict_data | safe }};
        const platformData = {{ platform_data | safe }};

        const vctx = document.getElementById('verdictChart').getContext('2d');
        new Chart(vctx, {
            type: 'pie',
            data: {
                labels: verdictData.labels,
                datasets: [{ data: verdictData.values, backgroundColor: ['#3fb950','#f85149','#d29922','#58a6ff'] }]
            },
            options: { responsive: true }
        });

        const pctx = document.getElementById('platformChart').getContext('2d');
        new Chart(pctx, {
            type: 'bar',
            data: {
                labels: platformData.labels,
                datasets: [{ label: 'Reports', data: platformData.values, backgroundColor: '#58a6ff' }]
            },
            options: { responsive: true, scales: { y: { beginAtZero: true } } }
        });
    </script>
</body>
</html>
""")


def _verdict_class(verdict: str) -> str:
    v = verdict.lower()
    if "false" in v or "misinformation" in v:
        return "verdict-false"
    elif "confirmed" in v or "true" in v:
        return "verdict-confirmed"
    return "verdict-unverified"


def generate_report_html(
    report_id: int,
    autopsy_md: str,
    overall_verdict: str,
    confidence: str,
    platform: str,
    author: str,
    created_at: str,
    agent_results: dict | None = None,
) -> str:
    """Render autopsy Markdown into a standalone HTML page and save to reports dir."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    body_html = _md_to_html(autopsy_md)
    title = f"Report #{report_id}"

    html = REPORT_TEMPLATE.render(
        title=title,
        platform=platform,
        author=author,
        created_at=created_at,
        overall_verdict=overall_verdict,
        confidence=confidence,
        verdict_class=_verdict_class(overall_verdict),
        body_html=body_html,
        agent_json=(json.dumps(agent_results, indent=2) if agent_results else None),
        key_findings_html=_build_key_findings_html(agent_results),
    )

    filepath = os.path.join(config.REPORTS_DIR, f"report_{report_id}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Saved HTML report to %s", filepath)
    return html


def regenerate_index(reports: list[dict]) -> None:
    """Regenerate the index.html that lists all reports."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    entries = []
    for r in reports:
        # Use autopsy_md if available to create a short HTML excerpt for the index
        autopsy_md = r.get('autopsy_md') or ''
        excerpt_html = ''
        if autopsy_md:
            # Take first 2 paragraphs / 300 chars
            excerpt = '\n\n'.join([p for p in autopsy_md.split('\n\n') if p.strip()][:2])
            excerpt = excerpt[:300]
            excerpt_html = _md_to_html(excerpt)

        # Parse agent_results if present
        agent_results = None
        ar_json = r.get('agent_results_json') or r.get('agent_results')
        try:
            if isinstance(ar_json, str) and ar_json.strip():
                agent_results = json.loads(ar_json)
            elif isinstance(ar_json, dict):
                agent_results = ar_json
        except Exception:
            agent_results = None

        entries.append(
            {
                "id": r["id"],
                "filename": f"report_{r['id']}.html",
                "overall_verdict": r.get("overall_verdict", "Unknown"),
                "verdict_class": _verdict_class(r.get("overall_verdict", "")),
                "platform": r.get("platform", ""),
                "created_at": r.get("created_at", ""),
                "excerpt_html": excerpt_html,
                "agent_results": agent_results,
                "key_findings_html": _build_key_findings_html(agent_results),
            }
        )

    html = INDEX_TEMPLATE.render(reports=entries)
    filepath = os.path.join(config.REPORTS_DIR, "index.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    # Build simple stats for charts
    verdict_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    for e in entries:
        v = e.get('overall_verdict', 'Unknown')
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        p = e.get('platform', 'unknown')
        platform_counts[p] = platform_counts.get(p, 0) + 1

    # Prepare JSON-like structures for template (Jinja will render them)
    verdict_data = {
        'labels': list(verdict_counts.keys()),
        'values': list(verdict_counts.values())
    }
    platform_data = {
        'labels': list(platform_counts.keys()),
        'values': list(platform_counts.values())
    }

    # Re-render with chart data injected
    html = INDEX_TEMPLATE.render(reports=entries, verdict_data=verdict_data, platform_data=platform_data)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Regenerated reports index.html with %d entries (charts included)", len(entries))


def _build_key_findings_html(agent_results: dict | None) -> str | None:
    """Build a small HTML block highlighting per-claim verdict, origin, and key evidence."""
    if not agent_results:
        return None

    checker = agent_results.get('claim_checker', {})
    tracer = agent_results.get('origin_tracer', {})
    counter = agent_results.get('counter_evidence', {})

    verdicts = checker.get('verdicts', []) if checker else []
    origins = tracer.get('origins', []) if tracer else []
    counter_list = counter.get('counter_evidence', []) if counter else []

    parts = ['<ul>']
    for v in verdicts:
        claim = v.get('claim', '')
        verdict = v.get('verdict', 'Unverified')
        explanation = v.get('explanation', '')
        key_evidence = v.get('key_evidence', '')

        # find matching origin and counter evidence
        o = next((o for o in origins if o.get('claim') == claim), {})
        ce = next((c for c in counter_list if c.get('claim') == claim), {})

        parts.append('<li style="margin-bottom:0.5rem;">')
        parts.append(f'<strong>Claim:</strong> {claim}<br/>')
        parts.append(f'<strong>Verdict:</strong> {verdict}<br/>')
        if key_evidence:
            parts.append(f'<strong>Key evidence:</strong> {key_evidence}<br/>')
        elif v.get('web_sources'):
            urls = [s.get('url') for s in v.get('web_sources', []) if s.get('url')][:2]
            if urls:
                parts.append(f'<strong>Evidence URLs:</strong> {", ".join(urls)}<br/>')

        if o and o.get('probable_origin'):
            parts.append(f'<strong>Probable origin:</strong> {o.get("probable_origin")}<br/>')
        if ce and ce.get('strongest_rebuttal'):
            parts.append(f'<strong>Counter-evidence:</strong> {ce.get("strongest_rebuttal")}<br/>')

        if explanation:
            parts.append(f'<em>{explanation}</em>')

        parts.append('</li>')

    parts.append('</ul>')
    return '\n'.join(parts)