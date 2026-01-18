#!/usr/bin/env python
"""Quick test script to verify OpenRouter API key."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    print("[X] No OPENROUTER_API_KEY found in .env")
    exit(1)

print(f"[OK] Found API key: {api_key[:20]}...")

# Test 1: Check key validity
print("\n1. Testing API key validity...")
response = requests.get(
    "https://openrouter.ai/api/v1/auth/key",
    headers={"Authorization": f"Bearer {api_key}"}
)

if response.status_code == 200:
    data = response.json()
    print(f"[OK] API key is valid!")
    print(f"  - Label: {data.get('data', {}).get('label', 'N/A')}")
    print(f"  - Limit: ${data.get('data', {}).get('limit', 'N/A')}")
    print(f"  - Usage: ${data.get('data', {}).get('usage', 'N/A')}")
else:
    print(f"[FAIL] API key test failed: {response.status_code}")
    print(f"   Response: {response.text}")
    exit(1)

# Test 2: Try a simple completion
print("\n2. Testing model access...")
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": "Say 'test successful' and nothing else"}],
        "max_tokens": 10
    }
)

if response.status_code == 200:
    data = response.json()
    content = data['choices'][0]['message']['content']
    print(f"[OK] Model works! Response: {content}")
elif response.status_code == 402:
    print("[FAIL] Payment Required - Add credits at https://openrouter.ai/credits")
elif response.status_code == 401:
    print("[FAIL] Unauthorized - Key might be invalid or revoked")
    print("   Generate new key at https://openrouter.ai/keys")
else:
    print(f"[FAIL] Request failed: {response.status_code}")
    print(f"   Response: {response.text}")

print("\n[OK] Test complete!")
