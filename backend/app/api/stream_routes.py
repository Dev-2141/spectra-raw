"""WebSocket live-update channel (Extension Step 7).

    ws://<host>/ws?token=<jwt>

Pushes ``state`` / ``decision`` / ``metric`` / ``alert`` events with a monotonic
per-type ``seq``. REST endpoints keep working unchanged; the frontend falls
back to polling if the socket drops.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth.tokens import TokenError, decode_token
from ..config import get_settings
from ..stream.hub import get_stream_hub

router = APIRouter(tags=["stream"])


@router.websocket("/ws")
async def ws_stream(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    try:
        decode_token(token, get_settings().jwt_key)
    except TokenError:
        await ws.close(code=1008)
        return

    await ws.accept()
    hub = get_stream_hub()
    try:
        hub.bind_loop(asyncio.get_running_loop())
    except RuntimeError:
        pass

    sub = hub.subscribe()
    await ws.send_json({"type": "hello", "seq": 0, "payload": {"ok": True}})
    try:
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=20.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "seq": 0, "payload": {}})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(sub)
