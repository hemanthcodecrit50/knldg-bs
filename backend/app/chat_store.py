"""SQLite-backed chat history store for conversational sessions."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "backend" / "data" / "chat_history.sqlite3"


def _resolve_db_path() -> Path:
    raw_path = os.getenv("CHAT_DB_PATH", str(_DEFAULT_DB_PATH))
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = (_REPO_ROOT / db_path).resolve()
    return db_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database() -> None:
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                citations_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id_id ON messages(chat_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC)")


def _row_to_chat(row: sqlite3.Row, message_count: int = 0, last_message_preview: str | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message_count": message_count,
        "last_message_preview": last_message_preview,
    }


def _derive_title(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    if not cleaned:
        return "New chat"
    if len(cleaned) <= 52:
        return cleaned
    return f"{cleaned[:49].rstrip()}…"


def create_chat(title: str | None = None) -> dict[str, Any]:
    chat_id = str(uuid.uuid4())
    now = _utc_now()
    chat_title = (title or "New chat").strip() or "New chat"

    with _connect() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, chat_title, now, now),
        )

    return {
        "id": chat_id,
        "title": chat_title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "last_message_preview": None,
    }


def get_chat(chat_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if row is None:
            return None
        count_row = conn.execute("SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?", (chat_id,)).fetchone()
        preview_row = conn.execute(
            "SELECT content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()

    return _row_to_chat(
        row,
        message_count=int(count_row["count"]) if count_row else 0,
        last_message_preview=preview_row["content"] if preview_row else None,
    )


def list_chats(limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chats ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        chats: list[dict[str, Any]] = []
        for row in rows:
            count_row = conn.execute("SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?", (row["id"],)).fetchone()
            preview_row = conn.execute(
                "SELECT content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            chats.append(
                _row_to_chat(
                    row,
                    message_count=int(count_row["count"]) if count_row else 0,
                    last_message_preview=preview_row["content"] if preview_row else None,
                )
            )
    return chats


def rename_chat(chat_id: str, title: str) -> None:
    clean_title = title.strip() or "New chat"
    with _connect() as conn:
        conn.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (clean_title, _utc_now(), chat_id))


def append_message(
    chat_id: str,
    role: str,
    content: str,
    citations: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    if role not in {"user", "assistant"}:
        raise ValueError(f"Unsupported role: {role}")

    created_at = _utc_now()
    citations_json = json.dumps(citations or [], ensure_ascii=False) if citations is not None else None

    with _connect() as conn:
        chat_row = conn.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if chat_row is None:
            raise KeyError(chat_id)

        cursor = conn.execute(
            """
            INSERT INTO messages (chat_id, role, content, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, role, content, citations_json, created_at),
        )

        if role == "user" and chat_row["title"] == "New chat":
            conn.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (_derive_title(content), created_at, chat_id),
            )
        else:
            conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (created_at, chat_id))

    return {
        "id": cursor.lastrowid,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "citations": citations or [],
        "created_at": created_at,
    }


def get_recent_messages(chat_id: str, limit: int = 12) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, chat_id, role, content, citations_json, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()

    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        citations = json.loads(row["citations_json"]) if row["citations_json"] else []
        messages.append(
            {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "role": row["role"],
                "content": row["content"],
                "citations": citations,
                "created_at": row["created_at"],
            }
        )
    return messages


def get_chat_detail(chat_id: str) -> dict[str, Any] | None:
    chat = get_chat(chat_id)
    if chat is None:
        return None
    return {"chat": chat, "messages": get_recent_messages(chat_id, limit=5000)}


def delete_chat(chat_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cursor.rowcount > 0

