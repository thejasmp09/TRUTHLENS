"""
TruthLens - main entry point.

Runs the poll -> filter -> analyze -> publish loop on a schedule.
Can also be run once with --once flag.
"""

import argparse
import os
import logging
import sys
import time
from dataclasses import asdict

import schedule

import config
from truthlens.db import (
    init_db,
    post_exists,
    save_post,
    mark_processed,
    get_unprocessed_posts,
    save_report,
    get_unpublished_reports,
    mark_published,
)
from truthlens.ingest.reddit import fetch_hot_posts
from truthlens.ingest.bluesky import fetch_popular_posts
from truthlens.ingest.news import fetch_news
from truthlens.filter import should_analyze
from truthlens.pipeline import analyze_post_with_agents
from truthlens.report import generate_report_html, regenerate_index
from truthlens.publish import publish_to_bluesky
import webbrowser
import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("truthlens")


def ingest() -> int:
    """Fetch posts from all sources, filter, and save candidates to DB."""
    saved = 0

    # --- Reddit ---
    for post in fetch_hot_posts():
        if post_exists(f"reddit:{post.id}"):
            continue
        if not should_analyze("reddit", post.content, post.score, num_comments=post.num_comments):
            continue
        save_post(
            post_id=f"reddit:{post.id}",
            platform="reddit",
            author=post.author,
            content=post.content,
            url=post.permalink,
            score=post.score,
        )
        saved += 1

    # --- Bluesky ---
    for post in fetch_popular_posts():
        if post_exists(f"bsky:{post.id}"):
            continue
        if not should_analyze("bluesky", post.content, post.score):
            continue
        save_post(
            post_id=f"bsky:{post.id}",
            platform="bluesky",
            author=post.author,
            content=post.content,
            url=post.url,
            score=post.score,
        )
        saved += 1

    # --- News ---
    for item in fetch_news():
        if post_exists(item.id):
            continue
        if not should_analyze("news", item.content, score=0):
            continue
        save_post(
            post_id=item.id,
            platform="news",
            author=item.source,
            content=item.content,
            url=item.url,
            score=0,
        )
        saved += 1

    logger.info("Ingestion complete: %d new candidates saved", saved)
    return saved


def process() -> int:
    """Analyze unprocessed posts and generate reports."""
    posts = get_unprocessed_posts()
    processed = 0

    for post in posts:
        try:
            report = analyze_post_with_agents(
                content=post["content"],
                source_url=post["url"],
                platform=post["platform"],
                author=post["author"],
            )

            if report is None:
                mark_processed(post["id"])
                continue

            # Serialize verdicts
            verdicts_data = []
            for v in report.verdicts:
                verdicts_data.append({
                    "claim": v.claim,
                    "verdict": v.verdict,
                    "explanation": v.explanation,
                    "evidence": v.evidence,
                    "existing_fact_checks": v.existing_fact_checks,
                })

            # Generate HTML
            html = generate_report_html(
                report_id=processed + 1,  # temporary, will be replaced by DB id
                autopsy_md=report.markdown,
                overall_verdict=report.overall_verdict,
                confidence=report.confidence,
                platform=post["platform"],
                author=post["author"],
                created_at=post["fetched_at"],
            )

            report_id = save_report(
                post_id=post["id"],
                claims=report.claims,
                verdicts=verdicts_data,
                autopsy_md=report.markdown,
                autopsy_html=html,
                overall_verdict=report.overall_verdict,
                confidence=report.confidence,
            )

            # Re-generate with correct ID
            generate_report_html(
                report_id=report_id,
                autopsy_md=report.markdown,
                overall_verdict=report.overall_verdict,
                confidence=report.confidence,
                platform=post["platform"],
                author=post["author"],
                created_at=post["fetched_at"],
            )

            mark_processed(post["id"])
            processed += 1
            logger.info("Report #%d generated for post %s", report_id, post["id"])

        except Exception:
            logger.exception("Failed to process post %s", post["id"])

    logger.info("Processing complete: %d reports generated", processed)
    return processed


def publish() -> int:
    """Publish unpublished reports to Bluesky."""
    reports = get_unpublished_reports()
    published = 0

    for report in reports:
        success = publish_to_bluesky(
            overall_verdict=report["overall_verdict"],
            confidence=report["confidence"],
            autopsy_md=report["autopsy_md"],
        )
        if success:
            mark_published(report["id"])
            published += 1

    # Regenerate index with all reports (including just-published)
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT r.id, r.overall_verdict, r.created_at, p.platform
           FROM reports r JOIN posts p ON r.post_id = p.id
           ORDER BY r.created_at DESC"""
    ).fetchall()
    conn.close()
    regenerate_index([dict(r) for r in rows])

    logger.info("Publishing complete: %d reports published", published)
    return published


def run_cycle() -> None:
    """One full cycle: ingest -> process -> publish."""
    logger.info("=" * 50)
    logger.info("Starting TruthLens cycle")
    logger.info("=" * 50)

    ingest()
    process()
    publish()

    logger.info("Cycle complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="TruthLens - Misinformation Autopsy Agent")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--schedule", action="store_true", help="Run continuous polling loop")
    parser.add_argument(
        "--interval", type=int, default=config.POLL_INTERVAL_MINUTES,
        help=f"Polling interval in minutes (default: {config.POLL_INTERVAL_MINUTES})",
    )
    args = parser.parse_args()

    # Validate minimum config
    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is required. Get one free at https://aistudio.google.com")
        sys.exit(1)

    has_source = config.REDDIT_CLIENT_ID or config.BLUESKY_HANDLE or config.NEWS_RSS_FEEDS
    if not has_source:
        logger.error("No data sources configured. Set Reddit, Bluesky, or news RSS credentials")
        sys.exit(1)

    init_db()
    logger.info("TruthLens initialized. DB: %s | Reports: %s/", config.DB_PATH, config.REPORTS_DIR)

    if args.once:
        run_cycle()
        # Regenerate index and open in default browser for immediate visual feedback
        try:
            conn = sqlite3.connect(config.DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT r.id, r.overall_verdict, r.created_at, p.platform
                   FROM reports r JOIN posts p ON r.post_id = p.id
                   ORDER BY r.created_at DESC"""
            ).fetchall()
            conn.close()
            regenerate_index([dict(r) for r in rows])
            index_path = os.path.abspath(os.path.join(config.REPORTS_DIR, "index.html"))
            webbrowser.open(f"file://{index_path}")
        except Exception:
            logger.exception("Failed to open reports index after run")
    elif args.schedule:
        logger.info("Scheduling every %d minutes. Press Ctrl+C to stop.", args.interval)
        run_cycle()  # Run immediately on start
        schedule.every(args.interval).minutes.do(run_cycle)
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down.")
    else:
        logger.info("Not running. Use --once to run a single cycle or --schedule to run continuously.")


if __name__ == "__main__":
    main()
