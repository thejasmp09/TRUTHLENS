"""
Bluesky ingestion via AT Protocol.
Polls search results and popular feeds.
"""

import logging
from dataclasses import dataclass

from atproto import Client

import config

logger = logging.getLogger(__name__)


@dataclass
class BlueskyPost:
    id: str
    author: str
    content: str
    url: str
    like_count: int
    repost_count: int

    @property
    def score(self) -> int:
        return self.like_count + 2 * self.repost_count
    

def _get_client() -> Client:
    client = Client()
    client.login(config.BLUESKY_HANDLE, config.BLUESKY_APP_PASSWORD)
    return client


def fetch_popular_posts(keywords: list[str] | None = None, limit: int = 30) -> list[BlueskyPost]:
    """Search Bluesky for posts matching keywords, sorted by relevance."""
    if not config.BLUESKY_HANDLE or not config.BLUESKY_APP_PASSWORD:
        logger.warning("Bluesky credentials not set - skipping Bluesky ingestion")
        return []
    
    if keywords is None:
        keywords = ["breaking news", "viral", "shocking", "exposed", "they don't want you to know"]
    client = _get_client()
    posts: list[BlueskyPost] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        try:
            response = client.app.bsky.feed.search_posts(
                params={"q": kw, "limit": min(limit, 25)}
            )

            candidates = getattr(response, "posts", []) or []
            for post_view in candidates:
                # Normalize access to the post/record/uri fields across client versions
                post_obj = getattr(post_view, "post", None) or getattr(post_view, "record", None) or post_view

                uri = None
                # try common places for the URI
                uri = getattr(post_obj, "uri", None) or getattr(post_view, "uri", None)
                if not uri:
                    # sometimes nested as post.uri
                    nested = getattr(post_view, "post", None)
                    uri = getattr(nested, "uri", None) if nested is not None else None
                if not uri:
                    continue
                if uri in seen_urls:
                    continue
                seen_urls.add(uri)

                # Extract record and text
                record = getattr(post_obj, "record", None) or post_obj
                text = getattr(record, "text", None) or str(record)

                # Author handle may be in post_view.author.handle or post_view.author
                author_handle = None
                if getattr(post_view, "author", None) is not None:
                    author = post_view.author
                    author_handle = getattr(author, "handle", None) or str(author)

                like_count = getattr(post_view, "like_count", None) or getattr(post_view, "likeCount", None) or 0
                repost_count = getattr(post_view, "repost_count", None) or getattr(post_view, "repostCount", None) or 0

                # Build web URL from URI: at://did/app.bsky.feed.post/rkey
                parts = uri.replace("at://", "").split("/")
                rkey = parts[-1] if parts else ""
                web_url = f"https://bsky.app/profile/{author_handle}/post/{rkey}" if author_handle else uri

                posts.append(
                    BlueskyPost(
                        id=uri,
                        author=author_handle or "",
                        content=text,
                        url=web_url,
                        like_count=int(like_count or 0),
                        repost_count=int(repost_count or 0),
                    )
                )
        except Exception:
            logger.exception("Bluesky search failed for keyword: %s", kw)

    logger.info("Fetched %d Bluesky posts", len(posts))
    return posts
