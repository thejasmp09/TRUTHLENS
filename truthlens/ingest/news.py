"""
News RSS feed ingestion.
"""

import logging
from dataclasses import dataclass

import feedparser

import config

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    url: str
    source: str

    @property
    def content(self) -> str:
        parts = [self.title]
        if self.summary:
            parts.append(self.summary)
        return "\n\n".join(parts)
    

def fetch_news(limits_per_feed: int = 10) -> list[NewsItem]:
    """Fetch recent news items from configured RSS feeds."""
    items: list[NewsItem] = []

    for feed_url in config.NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries[:limits_per_feed]:
                item_id = entry.get("id") or entry.get("link", "")
                items.append(
                    NewsItem(
                        id=f"news:{item_id}",
                        title=entry.get("title", ""),
                        summary=entry.get("summary", ""),
                        url=entry.get("link", ""),
                        source=source,
                    )
                )
        except Exception:
            logger.exception("Failed to parse RSS feed %s", feed_url)

    logger.info("Fetched %d news items from %d feeds", len(items), len(config.NEWS_RSS_FEEDS))
    return items
