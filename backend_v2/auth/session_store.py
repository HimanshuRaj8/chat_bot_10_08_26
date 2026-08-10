"""
Backend V2 — In-Memory Session Store

Simple in-process dict mapping session token → CurrentUser.
Thread-safe for single-process Flask dev; replace with Redis for multi-process prod.
"""
from typing import Dict, Optional
from models.user import CurrentUser


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, CurrentUser] = {}

    def store(self, token: str, user: CurrentUser) -> None:
        self._sessions[token] = user

    def get(self, token: str) -> Optional[CurrentUser]:
        return self._sessions.get(token)

    def remove(self, token: str) -> None:
        self._sessions.pop(token, None)

    def count(self) -> int:
        return len(self._sessions)
