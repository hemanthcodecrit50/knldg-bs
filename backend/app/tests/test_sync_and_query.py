"""
test_sync_and_query.py — Integration smoke test.

Requires an accessible Milvus-compatible vector database (for example, Zilliz Cloud) and valid API keys in the environment.

Usage:
        pytest backend/app/tests/test_sync_and_query.py -v
    or
        python backend/app/tests/test_sync_and_query.py
"""
import os
import sys
import tempfile
from pathlib import Path

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pytest
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_temp_md(content: str) -> Path:
    """Write a temporary Markdown file inside knowledge/ and return its path."""
    target_dir = Path(KNOWLEDGE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = target_dir / "_smoke_test_file.md"
    tmp.write_text(content, encoding="utf-8")
    return tmp


def _remove_temp_md(path: Path) -> None:
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    """Backend should return 200 /health."""
    resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok", f"Unexpected health response: {data}"
    print("[PASS] /health")


def test_sync_and_query():
    """
    End-to-end test:
      1. Write a unique fact to knowledge/.
      2. Run the sync engine.
      3. Query the API and assert the fact appears in citations.
    """
    unique_fact = "The Synced-Brain smoke test marker is XYZZY-42."
    tmp_path = _create_temp_md(
        f"# Smoke Test\n\n{unique_fact}\n\nThis file is created by the automated test suite."
    )

    try:
        # --- Step 1: Sync ---
        print("[TEST] Running sync …")
        # Import here so Milvus connection happens after env vars are set
        from backend.app.sync.sync import full_reconcile
        full_reconcile()
        print("[TEST] Sync complete.")

        # --- Step 2: Query ---
        print("[TEST] Querying /query …")
        payload = {
            "question": "What is the Synced-Brain smoke test marker?",
            "top_k": 5,
            "debug": True,
        }
        resp = requests.post(f"{BACKEND_URL}/query", json=payload, timeout=30)
        assert resp.status_code == 200, f"Query returned {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "answer" in data, "Response missing 'answer' field"
        assert "citations" in data, "Response missing 'citations' field"
        assert len(data["citations"]) > 0, "Expected at least one citation"

        # Check the unique marker appears somewhere in the retrieved chunks
        all_texts = " ".join(c["text"] for c in data["citations"])
        assert "XYZZY-42" in all_texts or "smoke test" in all_texts.lower(), (
            f"Unique marker not found in citations.\nTexts: {all_texts[:500]}"
        )
        print("[PASS] /query returned correct citation")

    finally:
        _remove_temp_md(tmp_path)
        # Re-sync to clean up the test file from Milvus
        from backend.app.sync.sync import full_reconcile
        full_reconcile()
        print("[CLEANUP] Temp file removed and re-synced.")


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Synced Brain Smoke Tests ===\n")
    test_health()
    test_sync_and_query()
    print("\n=== All tests passed ===")
