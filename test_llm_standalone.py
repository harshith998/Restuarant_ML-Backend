"""
Standalone test for LLM client (minimal dependencies).
Install: pip install httpx python-dotenv
Run: python test_llm_standalone.py
"""

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "bytedance-seed/seed-1.6")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = 30.0


async def test_llm_connection():
    """Test basic connection to OpenRouter API."""
    print("\n" + "="*60)
    print("Testing OpenRouter API Connection")
    print("="*60 + "\n")

    if not OPENROUTER_API_KEY:
        print("❌ ERROR: OPENROUTER_API_KEY not found in .env.local")
        print("Please add it to your .env.local file")
        return False

    print(f"✓ API Key found: {OPENROUTER_API_KEY[:20]}...")
    print(f"✓ Model: {OPENROUTER_MODEL}")
    print(f"✓ Endpoint: {OPENROUTER_ENDPOINT}\n")

    # Prepare test request
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Always respond in valid JSON format."},
            {"role": "user", "content": 'Say hello in JSON format: {"message": "your greeting", "status": "success"}'},
        ],
        "temperature": 0.5,
        "max_tokens": 200,
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/restaurant-intel",
        "X-Title": "Restaurant Intelligence Platform",
    }

    try:
        logger.info("Sending request to OpenRouter...")
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                OPENROUTER_ENDPOINT,
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                print(f"❌ API Error: Status {response.status_code}")
                print(f"Response: {response.text}")
                return False

            response_data = response.json()
            logger.info("Response received successfully")

            # Extract and parse content
            content = response_data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            print("✓ Connection successful!")
            print(f"✓ Response: {parsed}\n")

            # Validate structure
            if "message" in parsed and "status" in parsed:
                print("✓ JSON structure validated!")
                return True
            else:
                print("❌ JSON structure invalid")
                return False

    except httpx.TimeoutException:
        print(f"❌ Request timed out after {DEFAULT_TIMEOUT}s")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON response: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run test."""
    print("\n" + "="*60)
    print("OPENROUTER LLM CLIENT - STANDALONE TEST")
    print("="*60)

    success = await test_llm_connection()

    print("\n" + "="*60)
    if success:
        print("🎉 TEST PASSED - LLM Client is working!")
    else:
        print("❌ TEST FAILED - Please check configuration")
    print("="*60 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
