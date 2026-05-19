"""
Shared Gemini LLM client with automatic retry on rate limits.
All agents should use call_gemini() from here instead of calling the API directly.
"""

import logging
import re
import threading
import time

import config

logger = logging.getLogger(__name__)

_client = None

_last_call_time: float = 0.0
_MIN_CALL_GAP_SECONDS: float = 5.0
_call_lock = threading.Lock()

_MAX_RETRIES = 5
_DEFAULT_RETRY_WAIT = 60


def _get_client():
    global _client
    if _client is None:
        try:
            from google import genai
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
            logger.info("Gemini client initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize Gemini client: %s", e)
            raise
    return _client


def _parse_retry_delay(error_str: str) -> int:
    match = re.search(r"RetryDelay['\"]:\s*['\"](\d+)", error_str)
    if match:
        return int(match.group(1)) + 2
    match = re.search(r"retry in (\d+)", error_str)
    if match:
        return int(match.group(1)) + 2
    return _DEFAULT_RETRY_WAIT


_MODEL_FALLBACKS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite-001",
    "gemini-flash-lite-latest",
    "gemini-2.5-pro",
    "gemini-pro-latest",
]


def _is_daily_quota_exhausted(error_str: str) -> bool:
    return "PerDayPerProjectPerModel" in error_str


_exhausted_models: set = set()


def _try_fallback_model(current_model: str):
    _exhausted_models.add(current_model)
    for model in _MODEL_FALLBACKS:
        if model not in _exhausted_models:
            return model
    return None


def call_gemini(prompt: str) -> str:
    global _last_call_time

    if getattr(config, "MOCK_LLM", False):
        logger.warning(
            "MOCK_LLM=true in your .env — returning mock response. "
            "Set MOCK_LLM=false to enable real LLM analysis."
        )
        return (
            "VERDICT: Unverified\n"
            "EXPLANATION: LLM is disabled (mock mode). No real analysis performed.\n"
            "KEY EVIDENCE: None (mock response)"
        )

    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")

    client = _get_client()
    same_model_retries = 0

    while True:
        with _call_lock:
            elapsed = time.time() - _last_call_time
            if elapsed < _MIN_CALL_GAP_SECONDS:
                wait = _MIN_CALL_GAP_SECONDS - elapsed
                logger.debug("Rate limiting: sleeping %.2fs", wait)
                time.sleep(wait)
            _last_call_time = time.time()

        try:
            from google import genai
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            text = response.text.strip()
            logger.info("Gemini OK — %d chars via model %s", len(text), config.GEMINI_MODEL)
            return text

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            is_server_error = "503" in error_str or "UNAVAILABLE" in error_str

            if not is_rate_limit and not is_server_error:
                logger.error("Gemini call failed (non-retryable): %s", error_str)
                raise

            if _is_daily_quota_exhausted(error_str):
                fallback = _try_fallback_model(config.GEMINI_MODEL)
                if fallback:
                    logger.warning(
                        "Daily quota exhausted for '%s'. Switching to '%s'.",
                        config.GEMINI_MODEL, fallback,
                    )
                    config.GEMINI_MODEL = fallback
                    same_model_retries = 0
                    continue
                logger.error("Daily quota exhausted for ALL models. Wait until tomorrow.")
                raise

            same_model_retries += 1
            if same_model_retries > _MAX_RETRIES:
                raise RuntimeError(
                    f"Exceeded {_MAX_RETRIES} retries for model '{config.GEMINI_MODEL}'"
                )

            if is_server_error:
                wait = min(30 * same_model_retries, 120)
            else:
                wait = _parse_retry_delay(error_str)

            logger.warning(
                "Retry %d/%d for '%s'. Waiting %ds...",
                same_model_retries, _MAX_RETRIES, config.GEMINI_MODEL, wait,
            )
            time.sleep(wait)