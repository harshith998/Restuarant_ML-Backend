# LLM Client Quick Start

## Import
```python
from app.services.llm_client import call_llm
# or
from app.services import call_llm
```

## Basic Usage
```python
result = await call_llm(
    system_prompt="You are a helpful assistant. Respond in JSON.",
    user_prompt='Return this JSON: {"hello": "world"}',
    temperature=0.7  # Optional, default 0.7
)
# result = {"hello": "world"}
```

## Error Handling
```python
from app.services.llm_client import (
    call_llm,
    LLMError,
    LLMAuthError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMResponseError
)

try:
    result = await call_llm(system_prompt="...", user_prompt="...")
except LLMAuthError:
    # API key invalid or missing
    pass
except LLMRateLimitError:
    # Rate limit exceeded (already retried 3x)
    pass
except LLMTimeoutError:
    # Request timed out after 30s (already retried 3x)
    pass
except LLMResponseError:
    # Response wasn't valid JSON
    pass
except LLMError:
    # Other LLM errors
    pass
```

## Configuration
Located in `.env.local`:
```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=bytedance-seed/seed-1.6
```

## Features
- ✅ Async/await (non-blocking)
- ✅ Auto-retry with exponential backoff (3 attempts)
- ✅ JSON response parsing
- ✅ Request/response logging
- ✅ 30-second timeout per request
- ✅ Comprehensive error handling

## Quick Test
```bash
python test_llm_standalone.py
```

## Parameters
- `system_prompt` (str, required) - Defines AI behavior
- `user_prompt` (str, required) - The actual request
- `temperature` (float, optional) - 0.0-2.0, default 0.7
- `max_tokens` (int, optional) - Max response length, default 2000
- `response_format` (str, optional) - "json" (default)

## Example: Review Analysis
```python
system_prompt = """You are a review analyst.
Return JSON: {"sentiment": "positive/negative", "summary": "..."}"""

user_prompt = "Analyze: 'Great food, terrible service!'"

result = await call_llm(
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.7
)

print(result["sentiment"])  # "negative"
print(result["summary"])    # "Mixed review..."
```
