from __future__ import annotations

import asyncio
from typing import Any, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class DemoWebSocketManager:
    """Simple websocket connection manager for demo events."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)

        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(ws)


demo_ws_manager = DemoWebSocketManager()


def register_demo_websocket(app: FastAPI) -> None:
    """Register /ws/demo websocket endpoint."""

    @app.websocket("/ws/demo")
    async def demo_websocket(websocket: WebSocket) -> None:
        await demo_ws_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive; ignore client payloads for now.
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            await demo_ws_manager.disconnect(websocket)
        except Exception:
            await demo_ws_manager.disconnect(websocket)
