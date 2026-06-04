"""Unit tests for the SQLite chat history store."""
from __future__ import annotations

import importlib

from backend.app import chat_store


def test_chat_store_round_trip(tmp_path, monkeypatch):
    db_path = tmp_path / "chat_history.sqlite3"
    monkeypatch.setenv("CHAT_DB_PATH", str(db_path))

    module = importlib.reload(chat_store)
    module.initialize_database()

    chat = module.create_chat()
    assert chat["title"] == "New chat"

    first_message = module.append_message(chat["id"], "user", "What is the status of the deployment rollout?")
    module.append_message(chat["id"], "assistant", "The rollout is complete.")

    chats = module.list_chats()
    assert chats[0]["id"] == chat["id"]
    assert chats[0]["title"] == "What is the status of the deployment rollout?"
    assert chats[0]["message_count"] == 2

    detail = module.get_chat_detail(chat["id"])
    assert detail is not None
    assert detail["chat"]["id"] == chat["id"]
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["id"] == first_message["id"]
    assert detail["messages"][0]["role"] == "user"
