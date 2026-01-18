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
from app.services.chatbot_context import assemble_restaurant_context
from app.services.gemini_client import build_prompt, stream_gemini_response

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
    # 1. Assemble context from database
    try:
        context = await assemble_restaurant_context(restaurant_id, session)
    except Exception as e:
        raise HTTPException(500, f"Failed to get restaurant data: {e}")

    # 2. Build prompt
    history_dicts = [msg.model_dump() for msg in request.history]
    prompt = build_prompt(context, request.message, history_dicts)

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
