"""Gemini streaming client for chatbot via OpenRouter."""
from __future__ import annotations

import json
from typing import Generator

import httpx

from app.config import get_settings

# Get settings
settings = get_settings()
OPENROUTER_API_KEY = settings.openrouter_api_key
GEMINI_MODEL = settings.gemini_model
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def stream_gemini_response(prompt: str) -> Generator[str, None, None]:
    """
    Stream response from Gemini via OpenRouter API.

    Args:
        prompt: The full prompt to send to Gemini

    Yields:
        Text chunks as they arrive from the API

    Note:
        Uses OpenRouter's OpenAI-compatible API with streaming.
        FastAPI handles sync generators in StreamingResponse without issues.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": True,
    }

    with httpx.stream(
        "POST",
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60.0,
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if line.startswith("data: "):
                data = line[6:]  # Remove "data: " prefix

                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                except json.JSONDecodeError:
                    continue


def build_prompt(context: dict, message: str, history: list) -> str:
    """
    Build prompt from restaurant context, message, and conversation history.

    Args:
        context: Restaurant data context from chatbot_context service
        message: Current user message
        history: List of previous messages (ChatMessage dicts)

    Returns:
        Formatted prompt string for Gemini
    """
    # Build context summary
    context_text = f"""You are a helpful assistant for a restaurant manager.

Current Data:
- Reviews: {context['review_insights']['overall_average']} stars ({context['review_insights']['total_reviews']} total)
- Top menu items: {', '.join([item['name'] for item in context['menu_performance']['top_items'][:3]])}
- Staff: {context['staff_performance']['total_staff']} team members, top performer: {context['staff_performance']['top_performer']}
- Today's revenue: ${context['revenue_metrics']['today_revenue']:.2f} ({context['revenue_metrics']['today_covers']} covers)
- Active shifts: {context['scheduling_info']['active_shifts']}

Answer the manager's questions based on this data. Be helpful and concise."""

    # Add conversation history
    if history:
        context_text += "\n\nConversation History:\n"
        for msg in history[-10:]:  # Last 10 messages
            role = "Manager" if msg["role"] == "user" else "Assistant"
            context_text += f"{role}: {msg['content']}\n"

    # Add current message
    context_text += f"\n\nManager: {message}\nAssistant:"

    return context_text
