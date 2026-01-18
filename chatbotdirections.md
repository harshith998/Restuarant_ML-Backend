# Backend Specification: AI Chatbot Feature

**Document Version**: 1.0
**Date**: 2026-01-17
**Target LLM**: Google Gemini 3 Flash
**Priority**: High

---

## Overview

Implement a streaming chat API endpoint that allows restaurant managers to ask questions about their restaurant's performance. The endpoint will use Google Gemini 3 Flash to provide intelligent, context-aware responses based on aggregated restaurant data.

---

## 🎯 Requirements Summary

- **Endpoint**: `POST /api/v1/chat/{restaurant_id}/message`
- **Response Type**: Streaming (Server-Sent Events)
- **Context**: Aggregate data from reviews, menu, staff, scheduling, and revenue
- **Caching**: 5-minute TTL on restaurant context
- **LLM**: Google Gemini 3 Flash
- **History**: Support conversation history (last 10 messages)

---

## 📡 API Specification

### Endpoint

```
POST /api/v1/chat/{restaurant_id}/message
```

### Request Format

```json
{
  "message": "What are my top menu items this month?",
  "history": [
    {
      "role": "user",
      "content": "How are my reviews?"
    },
    {
      "role": "assistant",
      "content": "Your average rating is 4.2 stars..."
    }
  ]
}
```

**Fields**:
- `message` (string, required): The user's current question
- `history` (array, optional): Previous conversation messages for context
  - Each message has `role` ("user" or "assistant") and `content` (string)
  - Limit to last 10 messages

### Response Format (Streaming - Server-Sent Events)

```
event: message
data: {"type": "start", "message_id": "msg_abc123"}

event: message
data: {"type": "content", "content": "Based "}

event: message
data: {"type": "content", "content": "on "}

event: message
data: {"type": "content", "content": "your "}

event: message
data: {"type": "content", "content": "menu "}

event: message
data: {"type": "content", "content": "data, "}

...

event: message
data: {"type": "done", "message_id": "msg_abc123"}
```

**Stream Events**:
- `type: "start"` - Sent once at the beginning, includes message_id
- `type: "content"` - Sent for each chunk of text (word or phrase)
- `type: "done"` - Sent once at the end to signal completion

### Error Response (Non-Streaming)

```json
{
  "status": 400,
  "message": "Invalid request",
  "detail": "Message field is required"
}
```

**Error Codes**:
- `400` - Bad request (missing/invalid fields)
- `404` - Restaurant not found
- `500` - Internal server error (LLM failure, database error)
- `503` - Service unavailable (rate limit exceeded, LLM API down)

---

## 🗃️ Restaurant Context Assembly

Before calling the LLM, aggregate the following data to provide context. This context should be **cached for 5 minutes** to optimize performance.

### Data Sources to Aggregate

#### 1. Review Insights

**Source**: Existing review endpoints
- `GET /reviews/{restaurant_id}/summary`
- `GET /reviews/{restaurant_id}/stats`

**Data to Extract**:
```python
{
    "overall_average": 4.2,              # Average star rating
    "total_reviews": 156,                # Total review count
    "recent_summary": "Customers love...", # AI summary from /summary
    "category_opinions": {
        "food": "Excellent",
        "service": "Needs improvement",
        "atmosphere": "Great",
        "value": "Good",
        "cleanliness": "Excellent"
    },
    "needs_attention": true,             # Any flagged issues
    "trending_topics": [                 # Top keywords from recent reviews
        "slow service",
        "great ambiance",
        "small portions"
    ]
}
```

**Trending Topics Query** (SQL):
```sql
-- Extract trending keywords from reviews (past 30 days)
SELECT category, COUNT(*) as mentions, AVG(sentiment_score) as avg_sentiment
FROM reviews
WHERE restaurant_id = ?
  AND created_at > NOW() - INTERVAL '30 days'
  AND category_opinions IS NOT NULL
GROUP BY category
ORDER BY mentions DESC
LIMIT 5
```

---

#### 2. Menu Performance

**Source**: Existing menu endpoints
- `GET /restaurants/{restaurant_id}/menu/rankings/top?limit=5`
- `GET /restaurants/{restaurant_id}/menu/rankings/bottom?limit=5`
- `GET /restaurants/{restaurant_id}/menu/86-recommendations`

**Data to Extract**:
```python
{
    "top_items": [
        {"name": "Grilled Salmon", "orders_per_day": 12.5, "margin_pct": 65.2},
        {"name": "Caesar Salad", "orders_per_day": 10.3, "margin_pct": 78.1},
        ...
    ],
    "bottom_items": [
        {"name": "Mushroom Risotto", "orders_per_day": 0.8, "margin_pct": 22.3},
        ...
    ],
    "items_to_86": ["Mushroom Risotto", "Truffle Pasta"],
    "total_active_items": 42
}
```

---

#### 3. Staff Performance

**Source**: Database query (waiter performance tables)

**Data to Extract**:
```python
{
    "total_staff": 12,
    "top_performers": [
        {"name": "Sarah J.", "tier": "strong", "composite_score": 92.5},
        {"name": "Mike K.", "tier": "strong", "composite_score": 88.3},
        {"name": "Lisa M.", "tier": "standard", "composite_score": 82.1}
    ],
    "struggling_staff": [
        {"name": "Tom R.", "tier": "developing", "composite_score": 58.2},
        {"name": "Anna P.", "tier": "developing", "composite_score": 62.8}
    ],
    "avg_tips_per_cover": 3.45,
    "avg_efficiency": 87.5
}
```

**SQL Query**:
```sql
SELECT
    w.id,
    w.name,
    w.tier,
    wi.composite_score,
    AVG(ws.tips / NULLIF(ws.covers, 0)) as avg_tip_per_cover,
    AVG(ws.efficiency_pct) as avg_efficiency
FROM waiters w
LEFT JOIN waiter_insights wi ON w.id = wi.waiter_id
LEFT JOIN waiter_shifts ws ON w.id = ws.waiter_id
WHERE w.restaurant_id = ?
  AND w.is_active = TRUE
GROUP BY w.id, w.name, w.tier, wi.composite_score
ORDER BY wi.composite_score DESC
```

---

#### 4. Scheduling Information

**Source**: Existing schedule endpoints
- `GET /restaurants/{restaurant_id}/schedules?week_start={current_week}`

**Data to Extract**:
```python
{
    "current_week": "2026-01-13",        # Week start date
    "coverage_gaps": [
        {
            "day": "Tuesday",
            "time_slot": "6-9pm",
            "role": "server",
            "shortage": 2              # Need 2 more servers
        },
        ...
    ],
    "labor_cost_percent": 28.5,          # Labor as % of revenue
    "total_scheduled_hours": 320,
    "staffing_warnings": [
        "Understaffed Tuesday dinner",
        "No host scheduled for Sunday lunch"
    ]
}
```

**Coverage Gaps Query** (SQL):
```sql
SELECT
    shift_date,
    role,
    required_count,
    actual_count,
    (required_count - actual_count) as shortage
FROM (
    SELECT
        sr.shift_date,
        sr.role,
        sr.min_staff as required_count,
        COUNT(si.id) as actual_count
    FROM staffing_requirements sr
    LEFT JOIN schedule_items si
        ON sr.shift_date = si.shift_date
        AND sr.role = si.role
    WHERE sr.restaurant_id = ?
        AND sr.shift_date >= CURRENT_DATE
        AND sr.shift_date < CURRENT_DATE + INTERVAL '7 days'
    GROUP BY sr.shift_date, sr.role, sr.min_staff
) AS coverage
WHERE required_count > actual_count
ORDER BY shift_date, shortage DESC
```

---

#### 5. Revenue Metrics

**Source**: Database query (orders/transactions table)

**Data to Extract**:
```python
{
    "today_revenue": 2450.00,
    "today_covers": 85,
    "average_check": 28.82,
    "weekly_trend": "up",                # "up", "down", or "stable"
    "peak_hours": ["6-8pm", "12-2pm"]
}
```

**SQL Query** (example for today's revenue):
```sql
-- Today's revenue and covers
SELECT
    SUM(total_amount) as revenue,
    COUNT(DISTINCT order_id) as covers,
    AVG(total_amount) as avg_check
FROM orders
WHERE restaurant_id = ?
  AND order_date = CURRENT_DATE
```

**Weekly Trend Calculation**:
- Compare this week's revenue to last week
- If >5% increase: "up"
- If >5% decrease: "down"
- Otherwise: "stable"

---

### Complete Context Structure

The assembled context should look like this:

```python
restaurant_context = {
    "restaurant_info": {
        "id": "b0de4163-7bd0-439c-8220-2a789616a699",
        "name": "The Bistro",
        "timezone": "America/New_York"
    },
    "review_insights": { ... },      # See above
    "menu_performance": { ... },     # See above
    "staff_performance": { ... },    # See above
    "scheduling_info": { ... },      # See above
    "revenue_metrics": { ... }       # See above
}
```

---

## 🤖 LLM Integration (Google Gemini 3 Flash)

### Setup

```python
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-3-flash")
```

### System Prompt Template

```python
def build_system_prompt(context: dict) -> str:
    return f"""You are an AI assistant for restaurant managers using the Shire platform.
You help managers understand their restaurant's performance and make data-driven decisions.

Current Restaurant: {context['restaurant_info']['name']}
Current Date: {datetime.now().strftime('%Y-%m-%d')}

AVAILABLE DATA CONTEXT:

Reviews: {context['review_insights']['overall_average']} stars ({context['review_insights']['total_reviews']} total)
- Top praise: {get_top_category(context['review_insights']['category_opinions'])}
- Needs attention: {"Yes" if context['review_insights']['needs_attention'] else "No"}
- Trending topics: {', '.join(context['review_insights']['trending_topics'])}

Menu: {context['menu_performance']['total_active_items']} items active
- Top performer: {context['menu_performance']['top_items'][0]['name']} ({context['menu_performance']['top_items'][0]['orders_per_day']}/day)
- Consider removing: {', '.join(context['menu_performance']['items_to_86'])}

Staff: {context['staff_performance']['total_staff']} team members
- Top performer: {context['staff_performance']['top_performers'][0]['name']} ({context['staff_performance']['top_performers'][0]['tier']})
- Average efficiency: {context['staff_performance']['avg_efficiency']}%
- Struggling: {context['staff_performance']['struggling_staff'][0]['name']}

Schedule: Week of {context['scheduling_info']['current_week']}
- Labor cost: {context['scheduling_info']['labor_cost_percent']}%
- Coverage gaps: {len(context['scheduling_info']['coverage_gaps'])}
- Warnings: {', '.join(context['scheduling_info']['staffing_warnings'])}

Revenue: ${context['revenue_metrics']['today_revenue']:.2f} today ({context['revenue_metrics']['today_covers']} covers)
- Average check: ${context['revenue_metrics']['average_check']:.2f}
- Trend: {context['revenue_metrics']['weekly_trend']}
- Peak hours: {', '.join(context['revenue_metrics']['peak_hours'])}

GUIDELINES:
- Be conversational, helpful, and specific
- Reference actual data from the context when answering
- Provide actionable recommendations based on the data
- Use restaurant industry terminology appropriately
- Keep responses concise but informative (2-4 paragraphs max)
- When suggesting actions, explain the "why" behind them
- If the user asks about something not in the context, acknowledge the limitation

Remember: You're helping a busy restaurant manager make better decisions. Be practical and direct."""
```

### Generating Streaming Response

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

@router.post("/{restaurant_id}/message")
async def chat_message(restaurant_id: str, request: ChatRequest):
    # 1. Assemble context (with caching)
    context = await get_cached_restaurant_context(restaurant_id)

    # 2. Build system prompt
    system_prompt = build_system_prompt(context)

    # 3. Build full prompt (Gemini doesn't have separate system messages)
    # Include conversation history in the prompt
    conversation_text = ""
    if request.history:
        for msg in request.history:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            conversation_text += f"{role_label}: {msg['content']}\n\n"

    full_prompt = f"""{system_prompt}

CONVERSATION HISTORY:
{conversation_text}

USER: {request.message}

ASSISTANT:"""

    # 4. Generate streaming response
    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'start', 'message_id': generate_id()})}\n\n"

            response = model.generate_content(
                full_prompt,
                stream=True,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
            )

            for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk.text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            # Handle errors gracefully
            error_msg = f"Error generating response: {str(e)}"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
```

---

## 💾 Caching Strategy

### Redis Caching

**Cache Key Pattern**: `chat:context:{restaurant_id}`
**TTL**: 300 seconds (5 minutes)

```python
from aiocache import cached
from aiocache.serializers import JsonSerializer

@cached(
    ttl=300,
    key="chat:context:{restaurant_id}",
    serializer=JsonSerializer()
)
async def assemble_restaurant_context(restaurant_id: str) -> dict:
    """
    Assemble all restaurant context data.
    This function is cached for 5 minutes to optimize performance.
    """
    # Fetch all data in parallel for performance
    review_data = await fetch_review_insights(restaurant_id)
    menu_data = await fetch_menu_performance(restaurant_id)
    staff_data = await fetch_staff_performance(restaurant_id)
    schedule_data = await fetch_scheduling_info(restaurant_id)
    revenue_data = await fetch_revenue_metrics(restaurant_id)

    return {
        "restaurant_info": await get_restaurant_info(restaurant_id),
        "review_insights": review_data,
        "menu_performance": menu_data,
        "staff_performance": staff_data,
        "scheduling_info": schedule_data,
        "revenue_metrics": revenue_data
    }
```

### Cache Invalidation

Invalidate the cache when:
- New reviews are uploaded (`POST /reviews/{restaurant_id}/ingest`)
- Schedule is published (`POST /schedules/{schedule_id}/publish`)
- Menu items are 86'd or un-86'd (`POST /menu/items/{item_id}/86`)

```python
import aiocache

async def invalidate_chat_context(restaurant_id: str):
    """Invalidate the cached restaurant context"""
    cache = aiocache.Cache(aiocache.Cache.REDIS)
    await cache.delete(f"chat:context:{restaurant_id}")
```

---

## 🔧 Environment Variables

```env
# Google AI
GOOGLE_API_KEY=your_api_key_here

# Gemini Model
GEMINI_MODEL=gemini-3-flash

# Chat Configuration
CHAT_CONTEXT_TTL=300
MAX_CHAT_HISTORY=10

# Redis (for caching)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

---

## 📦 Dependencies

Add to `requirements.txt`:

```
google-generativeai>=0.3.0
aiocache>=0.12.0
redis>=5.0.0
```

Install:
```bash
pip install google-generativeai aiocache redis
```

---

## ✅ Testing Checklist

### Unit Tests

- [ ] Context assembly function returns correct structure
- [ ] System prompt builder includes all data sections
- [ ] Cache stores and retrieves context correctly
- [ ] Cache invalidation works on relevant endpoints

### Integration Tests

- [ ] Chat endpoint returns streaming response
- [ ] Streaming format matches specification (start/content/done)
- [ ] Conversation history is included in LLM prompt
- [ ] Errors are handled gracefully (missing restaurant, LLM failure)
- [ ] Cache reduces database queries (verify with logs)

### Manual Testing

- [ ] Send simple question: "How are my reviews?"
- [ ] Response references actual review data
- [ ] Send follow-up question with history
- [ ] Response maintains conversation context
- [ ] Test error handling (invalid restaurant_id)
- [ ] Test rate limiting (if implemented)
- [ ] Verify streaming is smooth (no long pauses)

### Performance Testing

- [ ] Context assembly completes in <2 seconds
- [ ] First streaming chunk arrives within 3 seconds
- [ ] Cache hit reduces response time by >50%
- [ ] Concurrent requests don't block each other

---

## 📊 Success Metrics

- **Response Time**: First chunk within 3 seconds
- **Context Accuracy**: Responses reference actual data 95%+ of time
- **Uptime**: 99.5%+ availability
- **Error Rate**: <2% of requests fail
- **Cache Hit Rate**: >80% of requests use cached context

---

## 🚀 Deployment Checklist

- [ ] Set `GOOGLE_API_KEY` in production environment
- [ ] Configure Redis for production (connection pooling, persistence)
- [ ] Set up monitoring for LLM API usage and costs
- [ ] Implement rate limiting (50 requests/hour per restaurant)
- [ ] Add request logging (anonymized user messages)
- [ ] Configure CORS for frontend domain
- [ ] Set up error alerting (Sentry, CloudWatch, etc.)
- [ ] Document API in Swagger/OpenAPI

---

## 💰 Cost Estimation

**Gemini 3 Flash Pricing**:
- **Free Tier**: 15 RPM, 1M TPM, 1500 RPD (should cover most usage)
- **Paid Tier**: ~$0.00002/1k tokens (input) + ~$0.00006/1k tokens (output)

**Average Request**:
- Input: ~2.5k tokens (context + history + user message)
- Output: ~1k tokens (response)
- Cost: ~$0.00011 per message

**Monthly Cost** (per restaurant):
- 50 messages/day × 30 days = 1500 messages/month
- Total: ~$0.17/month per restaurant
- **Free tier should cover this entirely** (up to 1500 requests/day)

---

## 🔐 Security Considerations

### Rate Limiting

Implement rate limiting to prevent abuse:
- **Limit**: 50 messages per restaurant per hour
- **Reset**: Rolling window or fixed window
- **Response**: HTTP 429 Too Many Requests

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/{restaurant_id}/message")
@limiter.limit("50/hour")
async def chat_message(...):
    ...
```

### Input Validation

- Validate restaurant_id exists in database
- Sanitize user message (max length: 500 characters)
- Validate history array (max 10 messages)
- Check message content for injection attempts

### API Key Security

- Store Google API key in environment variables (never in code)
- Use secrets manager in production (AWS Secrets Manager, Google Secret Manager)
- Rotate API keys regularly

---

## 📞 Support & Questions

If you have questions or need clarification on any part of this specification, please reach out to the frontend team.

**Document Owner**: Frontend Team
**Last Updated**: 2026-01-17
**Version**: 1.0
