# Basics

# Typing
from typing import Dict, Optional

# FastAPI
from fastapi import WebSocket

active_connections: Dict[str, WebSocket] = {}


def register_connection(socket_id: str, socket: WebSocket) -> None:
    """Save the websocket connection."""
    if socket_id not in active_connections:
        active_connections[socket_id] = socket


def get_connection(socket_id: str) -> Optional[WebSocket]:
    """Return a websocket connection."""
    if socket_id in active_connections:
        return active_connections[socket_id]
    return None


async def send_text(socket_id: str, text: str) -> None:
    """Send text through a websocket connection."""
    socket: WebSocket = get_connection(socket_id=str(socket_id))
    if socket:
        print('socket found')
        await socket.send_text(text)
    else:
        print(type(socket_id), type(active_connections))
        print(socket_id, active_connections.keys())
