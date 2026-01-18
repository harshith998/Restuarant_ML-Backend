# Track C: Chat Endpoint Integration (Terminal 3)

**Estimated Time:** 4-5 hours
**Dependencies:** Track A (Gemini Client) + Track B (Context Assembly)
**Owner:** Assign to Terminal/Developer 3

---

## Overview

Create the chat API endpoint that ties together the Gemini client and context assembly. This track should start after Tracks A and B are complete (or near completion).

---

## Hour-by-Hour Tasks

### Hour 1: Create Router with Schemas

**Tasks:**
1. Create new file: `app/api/chatbot.py`

2. Implement request/response schemas:
   ```python
   """Chatbot API endpoint."""
   from __future__ import annotations

   import json
   import uuid
   from uuid import UUID

   from fastapi import APIRouter, Depends, HTTPException
   from fastapi.responses import StreamingResponse
   from pydantic import BaseModel, Field
   from sqlalchemy.ext.asyncio import AsyncSession

   from app.database import get_session

   router = APIRouter(prefix="/api/v1/chat", tags=["chatbot"])


   # Request/Response schemas
   class ChatMessage(BaseModel):
       """Single message in conversation history."""
       role: str = Field(..., pattern="^(user|assistant)$")
       content: str


   class ChatRequest(BaseModel):
       """Chat request payload."""
       message: str = Field(..., min_length=1, max_length=500)
       history: list[ChatMessage] = Field(default_factory=list, max_length=10)

       class Config:
           json_schema_extra = {
               "example": {
                   "message": "How are my reviews?",
                   "history": [
                       {"role": "user", "content": "Hello"},
                       {"role": "assistant", "content": "Hi! How can I help?"}
                   ]
               }
           }
   ```

**Deliverable:** Router file with schemas

---

### Hour 2: Implement Stub Endpoint

**Tasks:**
1. Add stub endpoint to `app/api/chatbot.py`:
   ```python
   @router.post("/{restaurant_id}/message")
   async def chat_message(
       restaurant_id: UUID,
       request: ChatRequest,
       session: AsyncSession = Depends(get_session),
   ):
       """
       Streaming chat endpoint.
       Returns Server-Sent Events (SSE) stream.
       """
       # Stub implementation for testing
       def generate():
           message_id = str(uuid.uuid4())

           # Start event
           yield f"event: message\ndata: {json.dumps({'type': 'start', 'message_id': message_id})}\n\n"

           # Content event (stub)
           yield f"event: message\ndata: {json.dumps({'type': 'content', 'content': 'Hello! I am a stub response.'})}\n\n"

           # Done event
           yield f"event: message\ndata: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"

       return StreamingResponse(
           generate(),
           media_type="text/event-stream",
           headers={
               "Cache-Control": "no-cache",
               "Connection": "keep-alive",
           },
       )
   ```

**Deliverable:** Stub endpoint that returns SSE stream

---

### Hour 3: Register Router

**Tasks:**
1. Update `app/api/__init__.py`:
   ```python
   # Add import
   from app.api.chatbot import router as chatbot_router

   # Add to __all__
   __all__ = [
       # ... existing routers
       "chatbot_router",
   ]
   ```

2. Update `app/main.py` (around line 129):
   ```python
   # Import chatbot router
   from app.api import (
       restaurants_router,
       tables_router,
       waiters_router,
       shifts_router,
       waitlist_router,
       visits_router,
       routing_router,
       reviews_router,
       chatbot_router,  # ADD THIS
   )
   ```

3. Update `app/main.py` (around line 147):
   ```python
   # Register routers
   app.include_router(restaurants_router)
   app.include_router(tables_router)
   app.include_router(waiters_router)
   app.include_router(shifts_router)
   app.include_router(waitlist_router)
   app.include_router(visits_router)
   app.include_router(routing_router)
   app.include_router(reviews_router)
   app.include_router(chatbot_router)  # ADD THIS
   ```

4. Test stub endpoint:
   ```bash
   uvicorn app.main:app --reload
   ```

   Then in another terminal:
   ```bash
   curl -X POST http://localhost:8000/api/v1/chat/SOME-UUID/message \
     -H "Content-Type: application/json" \
     -d '{"message": "test", "history": []}'
   ```

**Deliverable:** Router registered, stub endpoint working

---

### Hour 4: Integrate Context Assembly (Track B)

**Tasks:**
1. Update endpoint to use real context (replace stub):
   ```python
   from app.services.chatbot_context import assemble_restaurant_context

   @router.post("/{restaurant_id}/message")
   async def chat_message(
       restaurant_id: UUID,
       request: ChatRequest,
       session: AsyncSession = Depends(get_session),
   ):
       """
       Streaming chat endpoint.
       Returns Server-Sent Events (SSE) stream.
       """
       # 1. Assemble context from database
       try:
           context = await assemble_restaurant_context(restaurant_id, session)
       except Exception as e:
           raise HTTPException(500, f"Failed to get restaurant data: {e}")

       # 2. For now, return context as test (before integrating Gemini)
       def generate():
           message_id = str(uuid.uuid4())

           yield f"event: message\ndata: {json.dumps({'type': 'start', 'message_id': message_id})}\n\n"

           # Test: return context summary
           content = f"Context loaded: {context['review_insights']['total_reviews']} reviews, "
           content += f"{context['staff_performance']['total_staff']} staff members"

           yield f"event: message\ndata: {json.dumps({'type': 'content', 'content': content})}\n\n"
           yield f"event: message\ndata: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"

       return StreamingResponse(
           generate(),
           media_type="text/event-stream",
           headers={
               "Cache-Control": "no-cache",
               "Connection": "keep-alive",
           },
       )
   ```

2. Test with real restaurant ID

**Deliverable:** Context assembly integrated

---

### Hour 5: Integrate Gemini Client (Track A)

**Tasks:**
1. Update endpoint with full implementation:
   ```python
   from app.services.chatbot_context import assemble_restaurant_context
   from app.services.gemini_client import build_prompt, stream_gemini_response

   @router.post("/{restaurant_id}/message")
   async def chat_message(
       restaurant_id: UUID,
       request: ChatRequest,
       session: AsyncSession = Depends(get_session),
   ):
       """
       Streaming chat endpoint.
       Returns Server-Sent Events (SSE) stream.
       """
       # 1. Assemble context from database
       try:
           context = await assemble_restaurant_context(restaurant_id, session)
       except Exception as e:
           raise HTTPException(500, f"Failed to get restaurant data: {e}")

       # 2. Build prompt
       prompt = build_prompt(context, request.message, request.history)

       # 3. Stream response from Gemini
       def generate():
           message_id = str(uuid.uuid4())

           try:
               # Start event
               yield f"event: message\ndata: {json.dumps({'type': 'start', 'message_id': message_id})}\n\n"

               # Stream content from Gemini
               for chunk in stream_gemini_response(prompt):
                   yield f"event: message\ndata: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

               # Done event
               yield f"event: message\ndata: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"

           except Exception as e:
               # Error event
               error_msg = f"Error generating response: {str(e)}"
               yield f"event: message\ndata: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"

       return StreamingResponse(
           generate(),
           media_type="text/event-stream",
           headers={
               "Cache-Control": "no-cache",
               "Connection": "keep-alive",
           },
       )
   ```

**Deliverable:** Full endpoint implementation

---

### Hour 6-7: Testing & Bug Fixes

**Tasks:**
1. Test various queries:
   ```bash
   # Test 1: Simple question
   curl -X POST http://localhost:8000/api/v1/chat/{restaurant_id}/message \
     -H "Content-Type: application/json" \
     -d '{"message": "How are my reviews?", "history": []}'

   # Test 2: With history
   curl -X POST http://localhost:8000/api/v1/chat/{restaurant_id}/message \
     -H "Content-Type: application/json" \
     -d '{
       "message": "What about my menu?",
       "history": [
         {"role": "user", "content": "How are my reviews?"},
         {"role": "assistant", "content": "Your reviews are 4.5 stars..."}
       ]
     }'

   # Test 3: Invalid restaurant ID
   curl -X POST http://localhost:8000/api/v1/chat/00000000-0000-0000-0000-000000000000/message \
     -H "Content-Type: application/json" \
     -d '{"message": "test", "history": []}'

   # Test 4: Message too long (should fail validation)
   curl -X POST http://localhost:8000/api/v1/chat/{restaurant_id}/message \
     -H "Content-Type: application/json" \
     -d '{"message": "'$(python -c 'print("x"*501)')'"}'
   ```

2. Verify:
   - ✅ Streaming works smoothly
   - ✅ Response references actual restaurant data
   - ✅ Conversation history is maintained
   - ✅ Errors return error events (not crashes)
   - ✅ Validation works (message length, history limit)

3. Fix any bugs found

**Deliverable:** Fully tested endpoint

---

### Hour 8: Documentation

**Tasks:**
1. Add API documentation to endpoint docstring:
   ```python
   @router.post("/{restaurant_id}/message")
   async def chat_message(
       restaurant_id: UUID,
       request: ChatRequest,
       session: AsyncSession = Depends(get_session),
   ):
       """
       Chat with AI assistant about restaurant performance.

       Streams responses using Server-Sent Events (SSE).

       **Request Body:**
       - `message`: User's question (1-500 characters)
       - `history`: Optional conversation history (max 10 messages)

       **Response Events:**
       - `start`: Stream begins, includes message_id
       - `content`: Text chunks as they arrive
       - `done`: Stream complete
       - `error`: If something goes wrong

       **Example:**
       ```
       POST /api/v1/chat/{restaurant_id}/message
       {
         "message": "How are my reviews?",
         "history": []
       }
       ```

       **Response:**
       ```
       event: message
       data: {"type": "start", "message_id": "..."}

       event: message
       data: {"type": "content", "content": "Based on "}

       event: message
       data: {"type": "content", "content": "your reviews..."}

       event: message
       data: {"type": "done", "message_id": "..."}
       ```
       """
   ```

2. Update `.env.example`:
   ```bash
   # Google AI (for chatbot)
   GOOGLE_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-3-flash
   ```

**Deliverable:** Documentation complete

---

## Completion Checklist

- [ ] `app/api/chatbot.py` created
- [ ] ChatMessage and ChatRequest schemas defined
- [ ] Router registered in `main.py` and `__init__.py`
- [ ] Context assembly integrated
- [ ] Gemini client integrated
- [ ] SSE streaming works correctly
- [ ] Error handling implemented
- [ ] All test cases pass
- [ ] API documentation added
- [ ] `.env.example` updated

---

## Integration Points

**Requires from Track A:**
- `app/services/gemini_client.py`
  - `stream_gemini_response()`
  - `build_prompt()`

**Requires from Track B:**
- `app/services/chatbot_context.py`
  - `assemble_restaurant_context()`

**Produces:**
- `/api/v1/chat/{restaurant_id}/message` endpoint

---

## Troubleshooting

**Issue:** Router not found at `/api/v1/chat`
- **Fix:** Verify router is imported and registered in `main.py`
- Check: Visit http://localhost:8000/docs to see all endpoints

**Issue:** SSE stream doesn't work in browser
- **Fix:** Use EventSource API:
  ```javascript
  const eventSource = new EventSource('/api/v1/chat/{id}/message');
  eventSource.onmessage = (e) => console.log(JSON.parse(e.data));
  ```

**Issue:** Context assembly fails
- **Fix:** Ensure Track B is complete and tested

**Issue:** Gemini streaming fails
- **Fix:** Ensure Track A is complete and GOOGLE_API_KEY is set

**Issue:** "Failed to get restaurant data"
- **Fix:** Verify restaurant_id exists in database
