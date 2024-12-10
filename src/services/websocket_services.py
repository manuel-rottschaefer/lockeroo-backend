"""Provides utility functions for the websocket backend."""

# Typing
from typing import Dict, Optional

# FastAPI
from fastapi import WebSocket

active_connections: Dict[str, WebSocket] = {}


def register_connection(socket_id: str, socket: WebSocket) -> None:
    """Save the websocket connection."""
    if socket_id not in active_connections:
        active_connections[socket_id] = socket


def unregister_connection(socket_id: str) -> None:
    """Remove the websocket connection."""
    if socket_id in active_connections:
        del active_connections[socket_id]


def get_connection(socket_id: str) -> Optional[WebSocket]:
    """Return a websocket connection."""
    if socket_id in active_connections:
        return active_connections[socket_id]
    return None


async def send_text(socket_id: str, text: str) -> None:
    """Send text through a websocket connection."""
    socket: WebSocket = get_connection(socket_id=str(socket_id))
    if socket:
        await socket.send_text(text)
