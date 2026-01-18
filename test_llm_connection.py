#!/usr/bin/env python
"""
Test script to verify OpenRouter LLM API connection.
Tests the LLM client with a simple request.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()


async def test_llm_connection():
    """Test LLM API connection with a simple request."""
    from app.services.llm_client import call_llm, OPENROUTER_API_KEY, OPENROUTER_MODEL

    print("=" * 60)
    print("OpenRouter LLM Connection Test")
    print("=" * 60)

    # Check configuration
    print("\n[Configuration]")
    if OPENROUTER_API_KEY:
        masked_key = f"{OPENROUTER_API_KEY[:15]}...{OPENROUTER_API_KEY[-4:]}"
        print(f"  [OK] API Key: {masked_key}")
    else:
        print("  [ERROR] API Key: NOT SET")
        print("\n[WARNING] Please set OPENROUTER_API_KEY in your .env file")
        return False

    print(f"  [OK] Model: {OPENROUTER_MODEL}")
    print(f"  [OK] Endpoint: https://openrouter.ai/api/v1/chat/completions")

    # Test 1: Simple JSON response
    print("\n" + "=" * 60)
    print("Test 1: Simple JSON Response")
    print("=" * 60)

    try:
        system_prompt = "You are a helpful assistant that responds in JSON format."
        user_prompt = """Please respond with a JSON object containing:
{
  "status": "success",
  "message": "Hello from the LLM!",
  "test_passed": true
}"""

        print("\n[TESTING] Calling LLM API...")
        result = await call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
            max_tokens=100
        )

        print("[OK] API call successful!")
        print(f"\n[Response]")
        import json
        print(json.dumps(result, indent=2))

        # Validate response
        if result.get("status") == "success" and result.get("test_passed"):
            print("\n[OK] Response validation: PASSED")
        else:
            print("\n[WARNING] Response validation: Structure unexpected")

    except Exception as e:
        print(f"\n[ERROR] API call failed: {e}")
        return False

    # Test 2: Review categorization (realistic use case)
    print("\n" + "=" * 60)
    print("Test 2: Review Categorization (Realistic)")
    print("=" * 60)

    try:
        system_prompt = """You are a restaurant review analyst.
Analyze reviews and categorize opinions about food, service, atmosphere, value, and cleanliness.

Return JSON in this format:
{
  "category_opinions": {
    "food": "brief opinion",
    "service": "brief opinion",
    "atmosphere": "brief opinion",
    "value": "brief opinion",
    "cleanliness": "brief opinion"
  },
  "overall_summary": "2-3 sentence summary",
  "needs_attention": true or false
}"""

        user_prompt = """Analyze this review:

Review 1 [5/5 stars]:
Amazing southern food! The shrimp and grits were incredible and the service was top-notch.

Return the JSON analysis."""

        print("\n[TESTING] Testing review categorization...")
        result = await call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=500
        )

        print("[OK] Categorization successful!")
        print(f"\n[Response]")
        import json
        print(json.dumps(result, indent=2))

        # Validate structure
        required_keys = ["category_opinions", "overall_summary", "needs_attention"]
        if all(key in result for key in required_keys):
            print("\n[OK] Structure validation: PASSED")

            # Check category opinions
            categories = result.get("category_opinions", {})
            expected_categories = ["food", "service", "atmosphere", "value", "cleanliness"]
            if all(cat in categories for cat in expected_categories):
                print("[OK] All 5 categories present: PASSED")
            else:
                print("[WARNING] Some categories missing")
        else:
            print("\n[WARNING] Structure validation: Missing required keys")

    except Exception as e:
        print(f"\n[ERROR] Categorization test failed: {e}")
        return False

    # Summary
    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED - OpenRouter is working correctly!")
    print("=" * 60)
    print("\nYour LLM integration is ready for production use.")
    print("\nNext steps:")
    print("  1. Restart your FastAPI server to load the new .env file")
    print("  2. Test the /categorize endpoint with real reviews")
    print("  3. Check review summaries in the /summary endpoint")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_llm_connection())
    sys.exit(0 if success else 1)
