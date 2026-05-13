"""
Bluesky auto-publisher.
Posts a summary thread for each autopsy report.
"""

import logging
import textwrap

from atproto import Client

import config

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    client = Client()
    client.login(config.BLUESKY_HANDLE, config.BLUESKY_APP_PASSWORD)
    return client


def _split_thread(text: str, max_len: int = 290) -> list[str]:
    """Split long text into thread-sized chunks (Bluesky limit is 300 chars)."""
    paragraphs = text.split("\n\n")
    posts: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_len:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                posts.append(current)
            # If paragraph itself is too long, wrap it
            if len(para) > max_len:
                wrapped = textwrap.wrap(para, width=max_len)
                posts.extend(wrapped)
                current = ""
            else:
                current = para

    if current:
        posts.append(current)

    return posts


def format_summary(
    overall_verdict: str,
    confidence: str,
    autopsy_md: str,
    report_url: str | None = None,
) -> str:
    """Create a concise summary suitable for a Bluesky post/thread."""
    # Extract the TL;DR section if it exists
    tldr = ""
    lines = autopsy_md.split("\n")
    in_tldr = False
    for line in lines:
        if "tl;dr" in line.lower() or "tldr" in line.lower() or "summary" in line.lower():
            in_tldr = True
            continue
        if in_tldr:
            if line.strip().startswith("#"):
                break
            if line.strip():
                tldr += line.strip() + " "

    tldr = tldr.strip()[:500] if tldr else "See full report for details."

    parts = [
        f"TruthLens Autopsy Report",
        f"Verdict: {overall_verdict} (Confidence: {confidence})",
        "",
        tldr,
    ]

    if report_url:
        parts.append("")
        parts.append(f"Full report: {report_url}")

    return "\n".join(parts)


def publish_to_bluesky(
    overall_verdict: str,
    confidence: str,
    autopsy_md: str,
    report_url: str | None = None,
) -> bool:
    """Publish an autopsy summary as a Bluesky post (or thread if long)."""
    if not config.BLUESKY_HANDLE or not config.BLUESKY_APP_PASSWORD:
        logger.warning("Bluesky credentials not set, skipping publish")
        return False

    summary = format_summary(overall_verdict, confidence, autopsy_md, report_url)
    chunks = _split_thread(summary)

    try:
        client = _get_client()

        parent_ref = None
        root_ref = None

        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk = f"({i + 1}/{len(chunks)}) {chunk}"

            if parent_ref is None:
                # First post in thread
                response = client.send_post(text=chunk)
                root_ref = {
                    "uri": response.uri,
                    "cid": response.cid,
                }
                parent_ref = root_ref
            else:
                # Reply to previous post
                response = client.send_post(
                    text=chunk,
                    reply_to={
                        "root": root_ref,
                        "parent": parent_ref,
                    },
                )
                parent_ref = {
                    "uri": response.uri,
                    "cid": response.cid,
                }

        logger.info("Published %d-post thread to Bluesky", len(chunks))
        return True

    except Exception:
        logger.exception("Failed to publish to Bluesky")
        return False
    