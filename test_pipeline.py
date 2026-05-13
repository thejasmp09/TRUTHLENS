"""
Quick smoke test – runs the multi-agent pipeline on a hardcoded fake post
without needing any API credentials (except Gemini).

Usage:
    export GEMINI_API_KEY=your_key_here
    python test_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import config
from truthlens.db import init_db
from truthlens.pipeline import analyze_post_with_agents
from truthlens.report import generate_report_html

SAMPLE_POST = "Raghav Chadha joined BJP"


def main():
    if not config.GEMINI_API_KEY:
        print("ERROR: Set GEMINI_API_KEY environment variable first.")
        print("Get a free key at https://aistudio.google.com/apikey")
        sys.exit(1)

    print("Initializing database...")
    init_db()

    print(f"\nAnalyzing sample post:\n \"{SAMPLE_POST}\" \n")

    report = analyze_post_with_agents(
        content=SAMPLE_POST,
        source_url="https://example.com/fake_post",
        platform="test",
        author="test_user",
    )

    if report is None:
        print("No checkable claims found.")
        return

    print("\n" + "=" * 60)
    print(f"Overall Verdict: {report.overall_verdict}")
    print(f"Confidence: {report.confidence}")
    print(f"Claims found: {len(report.claims)}")
    print("=" * 60 + "\n")

    for v in report.verdicts:
        print(f"Claim: {v.claim}")
        print(f"Verdict: {v.verdict}")
        print(f"Explanation: {v.explanation}")
        print()

    print("Full autopsy report (Markdown):")
    print("-" * 40)
    print(report.markdown)
    print("-" * 40)

    # Generate HTML
    html = generate_report_html(
        report_id=0,
        autopsy_md=report.markdown,
        overall_verdict=report.overall_verdict,
        confidence=report.confidence,
        platform="test",
        author="test_user",
        created_at="2026-04-25T00:00:00Z",
    )

    print(f"\nHTML report saved to: {config.REPORTS_DIR}/report_0.html")
    print("Open it in a browser to see the styled report.")


if __name__ == "__main__":
    main()
    