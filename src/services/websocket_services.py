"""Provides utility functions for the websocket backend."""
# Basics
import secrets
# Types
from typing import Dict, Optional
# FastAPI
from fastapi import WebSocket
# Beanie
from beanie import PydanticObjectId as ObjId

active_connections: Dict[ObjId, WebSocket] = {}


def generate_token() -> str:
    """Generate a random token."""
    return secrets.token_urlsafe(32)


def register_connection(session_id: ObjId, socket: WebSocket) -> None:
    """Save the websocket connection."""
    if session_id not in active_connections:
        active_connections[session_id] = socket


def unregister_connection(session_id: ObjId) -> None:
    """Remove the websocket connection."""
    if session_id in active_connections:
        del active_connections[session_id]


def get_connection(session_id: ObjId) -> Optional[WebSocket]:
    """Return a websocket connection."""
    if session_id in active_connections:
        return active_connections[session_id]
    return None


async def send_text(session_id: ObjId, text: str) -> None:
    """Send text through a websocket connection."""
    socket: WebSocket = get_connection(session_id=session_id)
    if socket:
        # logger.debug(
        #    f"Sending update for session '#{session_id}' over websocket channel.")
        await socket.send_text(text)
