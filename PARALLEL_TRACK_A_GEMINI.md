# Track A: Gemini Client Integration (Terminal 1)

**Estimated Time:** 3-4 hours
**Dependencies:** None - completely independent
**Owner:** Assign to Terminal/Developer 1

---

## Overview

Build the Google Gemini streaming client. This can be developed and tested completely independently from other components.

---

## Hour-by-Hour Tasks

### Hour 1: Setup & Basic Client

**Tasks:**
1. Install dependency:
   ```bash
   pip install google-generativeai>=0.3.0
   ```

2. Add to [requirements.txt](requirements.txt):
   ```txt
   google-generativeai>=0.3.0
   ```

3. Update [app/config.py](app/config.py) - add after line 53:
   ```python
   # Google AI (for chatbot)
   google_api_key: str | None = None
   gemini_model: str = "gemini-3-flash"
   ```

4. Create `.env.example` update:
   ```bash
   # Google AI
   GOOGLE_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-3-flash
   ```

**Deliverable:** Dependencies installed, config ready

---

### Hour 2: Create Gemini Client

**Tasks:**
1. Create new file: `app/services/gemini_client.py`

2. Implement streaming function:
   ```python
   """Google Gemini streaming client for chatbot."""
   from __future__ import annotations

   import os
   from typing import Generator

   import google.generativeai as genai

   # Configure Gemini
   GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
   GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")

   if GOOGLE_API_KEY:
       genai.configure(api_key=GOOGLE_API_KEY)


   def stream_gemini_response(prompt: str) -> Generator[str, None, None]:
       """
       Stream response from Gemini API.

       Args:
           prompt: The full prompt to send to Gemini

       Yields:
           Text chunks as they arrive from the API

       Note:
           Google SDK is synchronous, but FastAPI handles sync generators
           in StreamingResponse without issues.
       """
       if not GOOGLE_API_KEY:
           raise ValueError("GOOGLE_API_KEY environment variable not set")

       model = genai.GenerativeModel(GEMINI_MODEL)

       response = model.generate_content(
           prompt,
           stream=True,
           generation_config={
               "temperature": 0.7,
               "max_output_tokens": 1024,
           }
       )

       for chunk in response:
           if chunk.text:
               yield chunk.text
   ```

**Deliverable:** `gemini_client.py` with streaming function

---

### Hour 3: Add Prompt Builder

**Tasks:**
1. Add to `app/services/gemini_client.py`:
   ```python
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
   ```

**Deliverable:** Complete `gemini_client.py` with both functions

---

### Hour 4: Testing

**Tasks:**
1. Create test script `test_gemini_manual.py` in project root:
   ```python
   """Manual test for Gemini client."""
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
   ```

2. Run test:
   ```bash
   export GOOGLE_API_KEY="your_key_here"
   python test_gemini_manual.py
   ```

3. Verify:
   - ✅ API connects successfully
   - ✅ Streaming works (chunks arrive progressively)
   - ✅ Prompt includes restaurant data
   - ✅ Response is relevant to the question

**Deliverable:** Tested and working Gemini client

---

## Completion Checklist

- [ ] `google-generativeai` installed
- [ ] `requirements.txt` updated
- [ ] `app/config.py` has Google API settings
- [ ] `app/services/gemini_client.py` created
- [ ] `stream_gemini_response()` function works
- [ ] `build_prompt()` function works
- [ ] Manual test passes
- [ ] API key configured in `.env`

---

## Handoff to Track C

**Files to provide:**
- `app/services/gemini_client.py` - Complete and tested

**Functions available:**
- `stream_gemini_response(prompt: str) -> Generator[str, None, None]`
- `build_prompt(context: dict, message: str, history: list) -> str`

**Track C can import these** once this track is complete.

---

## Troubleshooting

**Issue:** `ImportError: No module named 'google.generativeai'`
- **Fix:** Run `pip install google-generativeai`

**Issue:** `ValueError: GOOGLE_API_KEY environment variable not set`
- **Fix:** Set in `.env` file or export: `export GOOGLE_API_KEY="your_key"`

**Issue:** API returns 401 Unauthorized
- **Fix:** Verify API key is correct at https://makersuite.google.com/app/apikey

**Issue:** Streaming not working
- **Fix:** Ensure `stream=True` in `generate_content()` call
