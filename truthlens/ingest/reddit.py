"""
Reddit data ingestion via PRAW.
Polls hot posts from configured subreddits.
"""

import logging
from dataclasses import dataclass

import praw

import config

logger = logging.getLogger(__name__)


@dataclass
class RedditPost:
    id: str
    subreddit: str
    author: str
    title: str
    selftext: str
    url: str
    score: int
    num_comments: int

    @property
    def content(self) -> str:
        """Full text content (title + body)."""
        parts = [self.title]
        if self.selftext:
            parts.append(self.selftext)
        return "\n\n".join(parts)
    
    @property
    def permalink(self) -> str:
        return f"https://www.reddit.com/r/{self.subreddit}/comments/{self.id}"
    
     
def _get_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
    )


def fetch_hot_posts(limit: int = 25) -> list[RedditPost]:
    """Fetch hot posts from configured subreddits."""
    if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
        logger.warning("Reddit credentials not set, skipping Reddit ingestion")
        return []
    
    reddit = _get_client()
    posts: list[RedditPost] = []

    for sub_name in config.REDDIT_SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name.strip())
            for submission in subreddit.hot(limit=limit):
                posts.append(
                    RedditPost(
                        id=submission.id,
                        subreddit=sub_name.strip(),
                        author=str(submission.author) if submission.author else "[deleted]",
                        title=submission.title,
                        selftext=submission.selftext or "",
                        url=submission.url,
                        score=submission.score,
                        num_comments=submission.num_comments,
                    )
                )
        except Exception:
            logger.exception("Failed to fetch posts from subreddit %s", sub_name)

    logger.info("Fetched %d Reddit posts from %d subreddits", len(posts), len(config.REDDIT_SUBREDDITS))
    return posts
