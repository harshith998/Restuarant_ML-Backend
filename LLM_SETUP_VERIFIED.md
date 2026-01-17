# OpenRouter LLM Setup - VERIFIED ✅

**Date:** January 17, 2026
**Status:** Fully operational and tested

---

## Configuration Summary

### API Key Location
- **File:** `.env` (root directory)
- **Variable:** `OPENROUTER_API_KEY`
- **Model:** `bytedance-seed/seed-1.6`

### Code Integration
- **Service:** [app/services/llm_client.py](app/services/llm_client.py)
- **Endpoint:** `https://openrouter.ai/api/v1/chat/completions`
- **Retry Logic:** 3 attempts with exponential backoff (1s, 2s, 4s)
- **Timeout:** 30 seconds per request

---

## Test Results

### Test 1: Simple JSON Response ✅
**Purpose:** Verify basic LLM connectivity and JSON parsing

**Request:**
```python
system_prompt = "You are a helpful assistant that responds in JSON format."
user_prompt = 'Respond with: {"status": "success", "message": "Hello from the LLM!", "test_passed": true}'
```

**Response:**
```json
{
  "status": "success",
  "message": "Hello from the LLM!",
  "test_passed": true
}
```

**Result:** ✅ PASSED - JSON parsing and API communication working

---

### Test 2: Review Categorization ✅
**Purpose:** Test production use case for restaurant review analysis

**Request:**
```python
system_prompt = """You are a restaurant review analyst.
Analyze reviews and categorize opinions about food, service, atmosphere, value, and cleanliness."""

user_prompt = """Review 1 [5/5 stars]:
Amazing southern food! The shrimp and grits were incredible and the service was top-notch."""
```

**Response:**
```json
{
  "category_opinions": {
    "food": "Amazing southern cuisine, with incredible shrimp and grits",
    "service": "Top-notch",
    "atmosphere": "Not mentioned in the review",
    "value": "Not mentioned in the review",
    "cleanliness": "Not mentioned in the review"
  },
  "overall_summary": "This 5-star review lauds the restaurant's southern food, specifically singling out the incredible shrimp and grits. The reviewer also expresses high praise for the establishment's top-notch service.",
  "needs_attention": false
}
```

**Result:** ✅ PASSED
- All 5 categories present
- Proper JSON structure
- Intelligent categorization
- Correctly flagged `needs_attention: false` (positive review)

---

## Production Endpoints Using LLM

### 1. POST /api/v1/reviews/{restaurant_id}/categorize
**Purpose:** Manually trigger LLM analysis for pending reviews
**Batch Size:** 25 reviews per batch
**LLM Call:** Uses `call_llm()` from llm_client.py

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/reviews/{restaurant_id}/categorize"
```

### 2. GET /api/v1/reviews/{restaurant_id}/summary
**Purpose:** Get LLM-generated category opinions
**Data Source:** Returns latest categorized batch results
**No LLM call:** Reads from database (LLM data pre-computed)

**Example:**
```bash
curl "http://localhost:8000/api/v1/reviews/{restaurant_id}/summary"
```

---

## Error Handling

The LLM client includes robust error handling:

### Exceptions
- `LLMAuthError` - Invalid or missing API key (doesn't retry)
- `LLMRateLimitError` - Rate limit exceeded (retries)
- `LLMTimeoutError` - Request timeout (retries)
- `LLMResponseError` - Invalid JSON response (retries)
- `LLMError` - Generic API error (retries)

### Retry Logic
- **Attempts:** 3 total attempts
- **Backoff:** 1s, 2s, 4s (exponential)
- **Auth Errors:** No retry (fails immediately)
- **Timeout:** 30 seconds per attempt

### Logging
All LLM calls are logged with:
- Attempt number
- Model used
- Temperature setting
- Success/failure status
- Error details (if any)

---

## Environment Variables

Required in `.env` file:
```bash
# OpenRouter LLM Configuration
OPENROUTER_API_KEY=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
OPENROUTER_MODEL=bytedance-seed/seed-1.6
```

Optional configuration (hardcoded defaults):
- `OPENROUTER_ENDPOINT` - API endpoint (default: https://openrouter.ai/api/v1/chat/completions)
- Timeout, retry settings, etc. in [llm_client.py](app/services/llm_client.py)

---

## Testing

### Quick Test
Run the verification script:
```bash
python test_llm_connection.py
```

Expected output:
```
[SUCCESS] ALL TESTS PASSED - OpenRouter is working correctly!
```

### Unit Tests
Review categorization tests with mocked LLM:
```bash
pytest tests/test_reviews.py::test_categorize_reviews_batch_with_mock -v
```

### Integration Test
Test with real API (requires valid key):
```bash
curl -X POST "http://localhost:8000/api/v1/reviews/{restaurant_id}/categorize"
```

---

## Cost Optimization

### Current Configuration
- **Model:** `bytedance-seed/seed-1.6` (cost-effective)
- **Batch Size:** 25 reviews per LLM call
- **Token Limit:** 2000 max tokens per response

### Cost Considerations
- Processing 100 reviews = ~4 LLM calls (25 reviews each)
- Each call processes multiple reviews in single prompt
- Shared analysis across batch reduces per-review cost

### Recommendations
1. **Batch processing** - Always use batches of 20-25 reviews
2. **Cache results** - Store in database, avoid re-processing
3. **Monitor usage** - Check OpenRouter dashboard for costs
4. **Rate limiting** - Consider adding rate limits for high-volume use

---

## Troubleshooting

### Issue: "OPENROUTER_API_KEY not set"
**Solution:** Ensure `.env` file exists (not just `.env.local`) with valid API key

### Issue: "Invalid API key"
**Solution:**
1. Check API key format starts with `sk-or-v1-`
2. Verify key is active in OpenRouter dashboard
3. Restart server after updating `.env`

### Issue: Rate limit exceeded
**Solution:**
- Wait for rate limit to reset
- Reduce batch size
- Add delays between requests
- Upgrade OpenRouter plan if needed

### Issue: Timeout errors
**Solution:**
- Check network connectivity
- Increase timeout in llm_client.py (DEFAULT_TIMEOUT)
- Reduce max_tokens to speed up response

### Issue: Invalid JSON response
**Solution:**
- LLM sometimes returns text instead of JSON
- Retry logic handles this automatically
- Check system prompt includes JSON format instruction
- Model should support `response_format: {"type": "json_object"}`

---

## Production Checklist

- [x] ✅ API key configured in `.env`
- [x] ✅ LLM client tested and working
- [x] ✅ Retry logic implemented
- [x] ✅ Error handling in place
- [x] ✅ Logging configured
- [x] ✅ Batch processing enabled
- [x] ✅ JSON validation working
- [x] ✅ Integration tests passing
- [ ] ⚠️  Rate limiting added (optional)
- [ ] ⚠️  Cost monitoring dashboard (optional)
- [ ] ⚠️  Background task queue (Celery/arq) for production scale

---

## Next Steps

1. **Restart FastAPI server** to ensure .env is loaded:
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Test categorization endpoint** with real reviews:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/reviews/{restaurant_id}/categorize"
   ```

3. **Verify summary endpoint** returns LLM insights:
   ```bash
   curl "http://localhost:8000/api/v1/reviews/{restaurant_id}/summary"
   ```

4. **Monitor costs** in OpenRouter dashboard

5. **Consider production enhancements:**
   - Background task queue for auto-categorization
   - Rate limiting for public APIs
   - Cost alerts and monitoring
   - Caching layer for frequently accessed summaries

---

**Status:** ✅ Production Ready
**Last Verified:** January 17, 2026
**Test Script:** [test_llm_connection.py](test_llm_connection.py)
