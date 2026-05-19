"""
Virality filter: decides which posts are worth analyzing.
Uses platform-specific thresholds + a quick LLM check for
whether the content contains checkable factual claims.
"""

import logging

import config
from truthlens.llm import call_gemini

logger = logging.getLogger(__name__)


def passes_virality_threshold(platform:str, score:int, **kwargs) -> bool:
    """Check if a post's score meets the platform-specific virality threshold."""
    if platform == "reddit":
        comments = kwargs.get("num_comments", 0)
        return (
            score >= config.REDDIT_SCORE_THRESHOLD
            or comments >= config.REDDIT_COMMENTS_THRESHOLD
        )
    elif platform == "bluesky":
        return score >= config.BLUESKY_LIKE_THRESHOLD
    elif platform == "news":
        # News items are already editorially selected; always pass
        return True
    return False


def contains_checkable_claims(text: str) -> bool:
    """
    Quick LLM check: does this text contain discrete, checkable factual claims
    (not just opinions or questions)?
    """
    if not config.GEMINI_API_KEY:
        logger.warning("No Gemini API key - skipping claim check, assuming True")
        return True
    
    prompt = (
        "You are a fact-check triage assistant. "
        "Does the following text contain at least one specific, checkable factual claim? "
        "A checkable claim is a statement that can be verified as true or false using evidence "
        "(not an opinion, question, or vague statement).\n\n"
        f"Text: \"{text[:1500]}\"\n\n"
        "Reply with ONLY 'yes' or 'no'."
    )

    try:
        # If running in mock mode, assume we should analyze so reports get populated
        if getattr(config, "MOCK_LLM", False):
            logger.info("MOCK_LLM enabled - skipping triage and assuming checkable claims")
            return True

        answer = call_gemini(prompt).lower()
        # Accept either strict 'yes' or presence of 'yes' in the reply
        return answer.strip().startswith("yes") or " yes" in answer
    except Exception:
        logger.exception("Gemini claim-check call failed, defaulting to True")
        return True
    

def should_analyze(platform:str, content:str, score:int, **kwargs) -> bool:
        """Full filter: virality threshold AND contains checkable claims."""
        if not passes_virality_threshold(platform, score, **kwargs):
            return False
        return contains_checkable_claims(content)
