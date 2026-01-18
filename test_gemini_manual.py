"""Manual test for Gemini client via OpenRouter.

Before running:
    export OPENROUTER_API_KEY="your_key_here"
    export GEMINI_MODEL="google/gemini-flash-1.5"  # Optional, has default
"""
import os
from app.services.gemini_client import stream_gemini_response, build_prompt

# Test 1: Direct streaming
print("Test 1: Direct streaming")
print("-" * 50)

for chunk in stream_gemini_response("Say hello in 5 words"):
    print(chunk, end="", flush=True)
print("\n")

# Test 2: With mock context
print("\nTest 2: With restaurant context")
print("-" * 50)

mock_context = {
    "review_insights": {"overall_average": 4.5, "total_reviews": 120},
    "menu_performance": {"top_items": [{"name": "Burger"}, {"name": "Pizza"}]},
    "staff_performance": {"total_staff": 8, "top_performer": "Alice"},
    "revenue_metrics": {"today_revenue": 2500.0, "today_covers": 75},
    "scheduling_info": {"active_shifts": 4}
}

prompt = build_prompt(mock_context, "How are my reviews?", [])
print(f"Generated prompt:\n{prompt}\n")

for chunk in stream_gemini_response(prompt):
    print(chunk, end="", flush=True)
print("\n")
