"""
Quick test script for LLM client functionality.
Run with: python -m asyncio test_llm_client.py
"""

import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")

from app.services.llm_client import call_llm

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_basic_call():
    """Test basic LLM call with JSON response."""
    print("\n" + "="*60)
    print("Testing LLM Client - Basic Call")
    print("="*60 + "\n")

    try:
        result = await call_llm(
            system_prompt="You are a helpful assistant. Always respond in JSON format.",
            user_prompt='Say hello in JSON format with this structure: {"message": "your greeting here", "status": "success"}',
            temperature=0.5
        )

        print("✓ LLM call successful!")
        print(f"Response: {result}")

        # Validate response structure
        assert "message" in result, "Response missing 'message' field"
        assert "status" in result, "Response missing 'status' field"

        print("\n✓ All assertions passed!")
        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_review_categorization():
    """Test LLM call simulating review categorization."""
    print("\n" + "="*60)
    print("Testing LLM Client - Review Categorization Simulation")
    print("="*60 + "\n")

    system_prompt = """You are a restaurant review analyst.
Analyze the provided review and generate category opinions.

Return JSON in this format:
{
  "category_opinions": {
    "food": "Brief opinion",
    "service": "Brief opinion"
  },
  "overall_summary": "2 sentence summary",
  "needs_attention": true or false
}"""

    user_prompt = """Analyze this review:

Review 1 [5/5 stars]:
Amazing southern food! The shrimp and grits were incredible and the service was top-notch.

Return the JSON analysis."""

    try:
        result = await call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7
        )

        print("✓ LLM call successful!")
        print(f"Response: {result}")

        # Validate response structure
        assert "category_opinions" in result, "Missing 'category_opinions'"
        assert "overall_summary" in result, "Missing 'overall_summary'"
        assert "needs_attention" in result, "Missing 'needs_attention'"

        print("\n✓ All assertions passed!")
        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("LLM CLIENT TEST SUITE")
    print("="*60)

    # Test 1: Basic call
    test1_passed = await test_basic_call()

    # Test 2: Review categorization simulation
    test2_passed = await test_review_categorization()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Basic Call: {'✓ PASSED' if test1_passed else '✗ FAILED'}")
    print(f"Review Categorization: {'✓ PASSED' if test2_passed else '✗ FAILED'}")
    print("="*60 + "\n")

    if test1_passed and test2_passed:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
