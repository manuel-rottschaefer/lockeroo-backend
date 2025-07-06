"""
Lockeroo.websocket_services
-------------------------
This module provides websocket utilities

Key Features:
    - Provides connection handlers
    - Provides token creation and data parsing

Dependencies:
    - fastapi
    - beanie
"""
# Basics
from typing import Dict, Optional
import asyncio
import secrets
# FastAPI & Beanie
from fastapi import WebSocket
from beanie import PydanticObjectId as ObjId
# Services
from src.services.logging_services import logger


class WebSocketManager():
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    def generate_token(self) -> str:
        """Generate a random token."""
        return secrets.token_urlsafe(32)

    def handle_socket_session(self, session_id: ObjId):
        """Launch an async task to keep the session alive."""

        async def _keep_alive():
            socket = self.get_connection(session_id=session_id)

            while True:
                try:
                    await asyncio.wait_for(socket.receive_bytes(), timeout=0.2)
                except asyncio.TimeoutError:
                    if websocketmanager.get_connection(session_id) is None:
                        logger.debug(
                            f"Session {session_id} websocket connection closed.", session_id=session_id)
                        break
                except Exception as e:
                    logger.error(
                        f"Error in keep-alive loop for session {session_id}: {e}", exc_info=True)
                    break

        asyncio.create_task(_keep_alive())

    def register_connection(self, session_id: ObjId, socket: WebSocket):
        """Save the websocket connection."""
        if str(session_id) not in self.active_connections:
            self.active_connections[str(session_id)] = socket

    def get_connection(self, session_id: ObjId) -> Optional[WebSocket]:
        """Return a websocket connection."""
        if str(session_id) in self.active_connections:
            return self.active_connections[str(session_id)]

    async def send_text(self, session_id: ObjId, data: str):
        """Send JSON through a websocket connection."""
        socket: WebSocket = self.get_connection(session_id=session_id)
        if socket is not None:
            await socket.send_json(data)


websocketmanager = WebSocketManager()
