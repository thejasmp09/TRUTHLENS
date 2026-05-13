"""
shared Gemini LLM client with automtic retry on rate limits.
All rounder should use call_gemini() from hre instead of calling the API directly.
"""

import logging
import re
import threading
import time

from google import genai

import config

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

# Rate limit: free tier is 15 RPM. We add a minimum gap between calls.
_last_call_time: float = 0.0
_MIN_CALL_GAP_SECONDS: float = 5.0 # ~12 calls/min - conservative for free tier
_call_lock = threading.Lock()

_MAX_RETRIES = 5
_DEFAULT_RETRY_WAIT = 60 # seconds


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _parse_retry_delay(error_str: str) -> int:
    """Extract retry delay from error message, e.g., 'RetryDelay': '57s'."""
    match = re.search(r"RetryDelay['\"]:\s*['\"](\d+)", error_str)
    if match:
        return int(match.group(1)) + 2 # add small buffer
    # Also try "please retry in X" pattern
    match = re.search(r"retry in (\d+)",error_str)
    if match:
        return int(match.group(1)) + 2
    return _DEFAULT_RETRY_WAIT


 # Models to try in order when daily quota is exhausted on the current model
_MODEL_FALLBACKS = [
     "gemini-2.5-flash",
     "gemini-2.0-flash",
     "gemini-2.0-flash-lite",
     "gemini-2.5-flash-lite",
     "gemini-flash-latest",
     "gemini-3-flash-preview",
     # -001 variants have seperate pper-model quotas
     "gemini-2.0-flash-001",
     "gemini-2.0-flash-lite-001",
     # additional models
     "gemini-flash-lite-latest",
     "gemini-2.5-pro",
     "gemini-pro-latest",
     "gemini-3-pro-preview",
     "gemini-3.1-pro-preview",
     "gemini-3.1-flash-lite-preview",
]


def _is_daily_quota_exhausted(error_str: str) -> bool:
    """
    Check if the error is a true daily quota exhaustion (not just per-minute).
    Detects by looking for the daily quota ID in the error details.
    """
    return "PerDayPerProjectPerModel" in error_str


_exhausted_models: set[str] = set()


def _try_fallback_model(current_model: str) -> str | None:
    """Return the next available fallback model, or None if all exhausted."""
    _exhausted_models.add(current_model)
    for model in _MODEL_FALLBACKS:
        if model not in _exhausted_models:
            return model
    return None


def call_gemini(prompt: str) -> str:
    """
    Single Gemini call with:
    - Rate limiting (minimum gap between calls)
    - Automatic retry with parsed delay on 429 rate-limit errors
    - Model switching on daily quota exhaustion (separate from retry counter)
    - Exponential backoff on 503 server errors
    """
    global _last_call_time

    client = _get_client()

    # Two independent counters:
    #   same_model_retries - retries on the CURRENT model (rate limits / 503s)
    #   model_switches - how many times we've swapped models (daily quota)
    same_model_retries = 0

    while True:
        # Thread-safe rate limiting
        with _call_lock:
            elapsed = time.time() - _last_call_time
            if elapsed < _MIN_CALL_GAP_SECONDS:
                wait = _MIN_CALL_GAP_SECONDS - elapsed
                logger.debug(f"Rate limiting: sleeping for {wait:.2f} seconds")
                time.sleep(wait)
            _last_call_time = time.time()

        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            return response.text.strip()
        
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            is_server_error = "503" in error_str or "UNAVAILABLE" in error_str

            if not is_rate_limit and not is_server_error:
                raise

            # Daily quota exhausted - switch model (doesn't count as a retry)
            if _is_daily_quota_exhausted(error_str):
                fallback = _try_fallback_model(config.GEMINI_MODEL)
                if fallback:
                    logger.warning(
                        "Daily quota exhausted for '%s'. Switching to '%s'.",
                        config.GEMINI_MODEL, fallback,
                    )
                    config.GEMINI_MODEL = fallback
                    same_model_retries = 0 # fresh retry budget for the new model
                    continue
                logger.error("Daily quota exhausted for all models. Wait until tomorrow.")
                raise

            # 503 or per-minute rate limit - retry same model up to _MAX_RETRIES
            same_model_retries += 1
            if same_model_retries > _MAX_RETRIES:
                raise RuntimeError(
                    f"Exceeded {_MAX_RETRIES} retries for model '{config.GEMINI_MODEL}'"
                )
            
            if is_server_error:
                wait = min(30 * same_model_retries, 120)
                logger.warning(
                    "Model '%s' unavailable (retry %d/%d). Waiting %ds...",
                    config.GEMINI_MODEL, same_model_retries, _MAX_RETRIES, wait,
                )
            else:
                wait = _parse_retry_delay(error_str)
                logger.warning(
                    "Rate limited on '%s' (retry %d/%d). Waiting %ds...",
                    config.GEMINI_MODEL, same_model_retries, _MAX_RETRIES, wait,
                )
            time.sleep(wait)
            