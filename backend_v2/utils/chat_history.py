"""
Backend V2 — Utilities: Chat History Manager

Persists and retrieves user chat sessions in a shared JSON file.
Compatible with the existing chat_history.json format.
"""
import json
import os
import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ChatHistoryManager:

    def __init__(self, history_file: str):
        self.history_file = history_file
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.history_file):
            with open(self.history_file, "w") as f:
                json.dump({}, f)

    def _load(self) -> dict:
        try:
            with open(self.history_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: dict):
        try:
            with open(self.history_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save chat history: {e}")

    def create_new_chat(self, user_key: str) -> str:
        data = self._load()
        chat_id = f"chat_{int(time.time() * 1000)}"
        if user_key not in data:
            data[user_key] = {}
        data[user_key][chat_id] = {
            "title": "New Chat",
            "created_at": time.time(),
            "messages": [],
        }
        self._save(data)
        return chat_id

    def add_message(self, user_key: str, chat_id: str, role: str, text: str):
        data = self._load()
        if user_key not in data or chat_id not in data[user_key]:
            return
        session = data[user_key][chat_id]
        session["messages"].append({"role": role, "text": text})
        # Auto-title from first user message
        if role == "user" and session.get("title") == "New Chat":
            session["title"] = text[:50] + ("..." if len(text) > 50 else "")
        self._save(data)

    def get_user_history(self, user_key: str) -> dict:
        data = self._load()
        return data.get(user_key, {})

    def get_chat(self, user_key: str, chat_id: str) -> Optional[dict]:
        data = self._load()
        return data.get(user_key, {}).get(chat_id)

    def delete_chat(self, user_key: str, chat_id: str) -> bool:
        data = self._load()
        if user_key in data and chat_id in data[user_key]:
            del data[user_key][chat_id]
            self._save(data)
            return True
        return False

    def get_recent_messages(self, user_key: str, chat_id: str, n: int = 4) -> List[dict]:
        """Returns last N messages for conversational context."""
        session = self.get_chat(user_key, chat_id)
        if not session:
            return []
        return session.get("messages", [])[-n:]
