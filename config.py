"""
TruthLens configuration.
Loads all secrets/settings from .env safely.
"""

from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# ============================================================================
# REDDIT
# ============================================================================

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "TruthLens/0.1")

# Clean subreddit parsing
REDDIT_SUBREDDITS = [
    s.strip()
    for s in os.environ.get(
        "REDDIT_SUBREDDITS",
        "news,worldnews,politics,health,technology"
    ).split(",")
]

# ============================================================================
# BLUESKY
# ============================================================================

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")

# ============================================================================
# GOOGLE GEMINI
# ============================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Validate required key
if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is required. "
        "Add it to your .env file."
    )

# ============================================================================
# VIRALITY THRESHOLDS
# ============================================================================

REDDIT_SCORE_THRESHOLD = int(
    os.environ.get("REDDIT_SCORE_THRESHOLD", "500")
)

REDDIT_COMMENT_THRESHOLD = int(
    os.environ.get("REDDIT_COMMENT_THRESHOLD", "100")
)

BLUESKY_LIKE_THRESHOLD = int(
    os.environ.get("BLUESKY_LIKE_THRESHOLD", "50")
)

# ============================================================================
# POLLING
# ============================================================================

POLL_INTERVAL_MINUTES = int(
    os.environ.get("POLL_INTERVAL_MINUTES", "10")
)

# ============================================================================
# STORAGE PATHS
# ============================================================================

DB_PATH = os.environ.get("TRUTHLENS_DB", "truthlens.db")

REPORTS_DIR = os.environ.get(
    "TRUTHLENS_REPORTS_DIR",
    "reports"
)

# ============================================================================
# NEWS RSS FEEDS
# ============================================================================

NEWS_RSS_FEEDS = [
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.reuters.com/reuters/worldNews",
    "https://feeds.npr.org/1001/rss.xml"
]

# ============================================================================
# DEBUG (Optional)
# ============================================================================

print("====================================")
print("TruthLens Configuration Loaded")
print("====================================")
print("Gemini Model:", GEMINI_MODEL)
print("Gemini Key Loaded:", bool(GEMINI_API_KEY))
print("Subreddits:", REDDIT_SUBREDDITS)
print("Database:", DB_PATH)
print("Reports Directory:", REPORTS_DIR)
print("====================================")

# Allow running without an LLM by using a deterministic mock (for testing)
MOCK_LLM = os.environ.get("MOCK_LLM", "false").lower() in ("1", "true", "yes")