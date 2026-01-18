"""
LLM Client Service - OpenRouter Integration

Provides async LLM calls to OpenRouter API with retry logic,
error handling, and JSON response parsing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OpenRouter Configuration
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


from typing import Optional


def get_api_key() -> Optional[str]:
    """Get API key at runtime (allows for late .env loading)."""
    # Try env var first, then fall back to settings
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # Import here to avoid circular imports
        from app.config import get_settings
        settings = get_settings()
        api_key = settings.openrouter_api_key or settings.llm_api_key
    return api_key


def get_model() -> str:
    """Get model at runtime."""
    model = os.getenv("OPENROUTER_MODEL")
    if not model:
        from app.config import get_settings
        settings = get_settings()
        model = settings.openrouter_model or settings.llm_model
    return model or "google/gemini-3-flash-preview"

# Request settings
DEFAULT_TIMEOUT = 30.0  # seconds
RETRY_ATTEMPTS = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff delays


class LLMError(Exception):
    """Base exception for LLM client errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    pass


class LLMAuthError(LLMError):
    """Raised when API key is invalid or missing."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limit is exceeded."""
    pass


class LLMResponseError(LLMError):
    """Raised when response cannot be parsed as JSON."""
    pass


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    response_format: str = "json",
) -> dict[str, Any]:
    """
    Call OpenRouter LLM API with retry logic.

    Args:
        system_prompt: System prompt defining AI behavior and task
        user_prompt: User prompt with the actual request/data
        temperature: Sampling temperature (0.0-2.0), default 0.7
        max_tokens: Maximum tokens in response, default 2000
        response_format: Expected response format, default "json"

    Returns:
        Parsed JSON response as dictionary

    Raises:
        LLMAuthError: If API key is invalid or missing
        LLMRateLimitError: If rate limit is exceeded
        LLMTimeoutError: If request times out
        LLMResponseError: If response cannot be parsed as JSON
        LLMError: For other API errors

    Example:
        >>> result = await call_llm(
        ...     system_prompt="You are a helpful assistant.",
        ...     user_prompt='Say hello in JSON: {"message": "..."}',
        ...     temperature=0.5
        ... )
        >>> print(result["message"])
    """
    # Get API key and model at runtime
    api_key = get_api_key()
    model = get_model()

    # Validate API key
    if not api_key:
        raise LLMAuthError(
            "OPENROUTER_API_KEY not set in environment variables. "
            "Please add it to your .env file."
        )

    # Prepare request payload
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Add response format hint if JSON expected
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/restaurant-intel",  # Optional: for OpenRouter analytics
        "X-Title": "Restaurant Intelligence Platform",  # Optional: for OpenRouter analytics
    }

    # Retry loop with exponential backoff
    last_exception = None

    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info(
                f"LLM API call attempt {attempt + 1}/{RETRY_ATTEMPTS} "
                f"(model: {model}, temp: {temperature})"
            )

            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    OPENROUTER_ENDPOINT,
                    json=payload,
                    headers=headers,
                )

                # Handle HTTP errors
                if response.status_code == 401:
                    raise LLMAuthError(
                        f"Invalid API key. Status: {response.status_code}"
                    )
                elif response.status_code == 429:
                    logger.warning("Rate limit exceeded, retrying...")
                    raise LLMRateLimitError("Rate limit exceeded")
                elif response.status_code >= 400:
                    error_detail = response.text
                    logger.error(
                        f"LLM API error {response.status_code}: {error_detail}"
                    )
                    raise LLMError(
                        f"API request failed with status {response.status_code}: {error_detail}"
                    )

                # Parse response
                response_data = response.json()
                logger.debug(f"LLM API response: {response_data}")

                # Extract content from OpenRouter response format
                content = response_data["choices"][0]["message"]["content"]

                # Parse JSON response
                try:
                    parsed_content = json.loads(content)
                    logger.info("LLM API call successful")
                    return parsed_content
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {content}")
                    raise LLMResponseError(
                        f"LLM response is not valid JSON: {e}"
                    )

        except httpx.TimeoutException as e:
            logger.warning(f"Request timeout on attempt {attempt + 1}")
            last_exception = LLMTimeoutError(f"Request timed out after {DEFAULT_TIMEOUT}s")

        except LLMAuthError:
            # Don't retry auth errors
            raise

        except (LLMRateLimitError, LLMError, httpx.HTTPError) as e:
            logger.warning(f"Error on attempt {attempt + 1}: {e}")
            last_exception = e

        # Wait before retry (exponential backoff)
        if attempt < RETRY_ATTEMPTS - 1:
            delay = RETRY_DELAYS[attempt]
            logger.info(f"Retrying in {delay} seconds...")
            import asyncio
            await asyncio.sleep(delay)

    # All retries exhausted
    error_msg = f"LLM API call failed after {RETRY_ATTEMPTS} attempts"
    logger.error(error_msg)
    if last_exception:
        raise last_exception
    raise LLMError(error_msg)
