"""
sync.py — RAG-Ops Sync Engine.

Reconciles the `knowledge/` folder against Milvus:
  • ADDED    → parse + embed + upsert
  • MODIFIED → delete old chunks, then upsert new
  • DELETED  → delete all chunks for that file
  • UNCHANGED → skip

Run modes:
  Full reconcile (default, safe to run anytime):
      python -m backend.app.sync.sync

  Git-diff mode (faster, used in CI after a push):
      python -m backend.app.sync.sync --git-diff HEAD~1 HEAD
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Make sure the repo root is importable regardless of CWD
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

try:
    import cohere  # noqa: E402
except Exception:  # pragma: no cover - optional runtime dependency
    cohere = None

from backend.app.ingestion.chunking import chunk_pages  # noqa: E402
from backend.app.ingestion.parsers import parse_file  # noqa: E402
from backend.app.sync.hashing import file_content_hash, file_doc_id, make_chunk_id  # noqa: E402
from backend.app.vectorstore.milvus_store import (  # noqa: E402
    delete_by_source,
    get_all_sources,
    get_existing_hash,
    get_or_create_collection,
    upsert_chunks,
)

load_dotenv(_REPO_ROOT / "backend" / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
EMBED_MODEL = "embed-english-v3.0"
EMBED_BATCH = 96      # Cohere max batch size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(path: str) -> str:
    """Normalise a path to POSIX-style (forward slashes)."""
    return Path(path).as_posix()


def _discover_files(base_dir: str) -> list[str]:
    base = Path(base_dir)
    if not base.exists():
        print(f"[WARN] Knowledge directory '{base_dir}' does not exist — nothing to sync.")
        return []
    files: list[str] = []
    for glob in ("**/*.md", "**/*.pdf"):
        files.extend(str(p) for p in base.glob(glob))
    return sorted(files)


def _get_embeddings(texts: list[str]) -> list[list[float]]:
    if cohere is None:
        raise RuntimeError("cohere package is not installed")

    co = cohere.Client(COHERE_API_KEY)
    all_embs: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = co.embed(texts=batch, model=EMBED_MODEL, input_type="search_document")
        all_embs.extend(resp.embeddings)
    return all_embs


def _git_changed_files(base: str, head: str) -> dict[str, str]:
    """
    Run `git diff --name-status <base> <head>` and return {path: status}.
    Status values: 'A' (added), 'M' (modified), 'D' (deleted).
    """
    result = subprocess.run(
        ["git", "diff", "--name-status", base, head],
        capture_output=True, text=True, check=True,
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            status, path = parts[0][0], parts[1].strip()   # first char only (handles 'R100' etc.)
            if path.startswith(KNOWLEDGE_DIR + "/") and (path.endswith(".md") or path.endswith(".pdf")):
                mapping[path] = status
    return mapping


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

def _process_file(
    col,
    file_path: str,
    action: str,
    content_hash: str,
    source_override: str | None = None,
) -> int:
    """Parse, embed, and upsert one file. Deletes old chunks if MODIFIED."""
    source = source_override or _norm(file_path)

    try:
        pages = parse_file(file_path)
        chunks = chunk_pages(pages)
    except Exception as exc:
        print(f"  [ERROR] Could not parse {file_path}: {exc}")
        return 0

    if not chunks:
        print(f"  [WARN] No text extracted from {file_path} — skipping.")
        return 0

    if action == "MODIFIED":
        delete_by_source(col, source)

    doc_id = file_doc_id(source)
    last_modified = str(int(time.time()))
    doc_type = Path(file_path).suffix.lstrip(".")
    texts = [c["chunk_text"] for c in chunks]

    try:
        embeddings = _get_embeddings(texts)
    except Exception as exc:
        print(f"  [ERROR] Embedding failed for {file_path}: {exc}")
        return 0

    records = [
        {
            "id":            make_chunk_id(doc_id, idx),
            "embedding":     emb,
            "source":        source,
            "content_hash":  content_hash,
            "chunk_index":   idx,
            "chunk_text":    chunk["chunk_text"],
            "last_modified": last_modified,
            "doc_type":      doc_type,
            "page":          chunk.get("page") or -1,
        }
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    upsert_chunks(col, records)
    print(f"  → upserted {len(records)} chunks")
    return len(records)


def sync_single_file(file_path: str) -> dict:
    """
    Sync a single markdown/pdf file into Milvus.

    Returns:
        dict with {action, source, chunks}
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() not in {".md", ".pdf"}:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    col = get_or_create_collection()
    try:
        source = _norm(str(path.relative_to(_REPO_ROOT)))
    except ValueError:
        source = _norm(str(path))

    content_hash = file_content_hash(str(path))
    existing_hash = get_existing_hash(col, source)

    if existing_hash == content_hash:
        return {"action": "UNCHANGED", "source": source, "chunks": 0}

    action = "ADDED" if existing_hash is None else "MODIFIED"
    chunk_count = _process_file(
        col,
        str(path),
        action,
        content_hash,
        source_override=source,
    )
    return {"action": action, "source": source, "chunks": chunk_count}


def sync_deleted_source(source: str) -> dict:
    """
    Remove one source path from Milvus when the backing file is deleted.

    Args:
        source: Repository-relative source path stored in Milvus.

    Returns:
        dict with {action, source, chunks}
    """
    norm_source = _norm(source)
    col = get_or_create_collection()
    delete_by_source(col, norm_source)
    return {"action": "DELETED", "source": norm_source, "chunks": 0}


def full_reconcile() -> None:
    """Compare every file in knowledge/ against Milvus state."""
    print(f"[SYNC] Full reconcile from '{KNOWLEDGE_DIR}' …")
    col = get_or_create_collection()

    candidate_files = _discover_files(KNOWLEDGE_DIR)
    candidate_sources = {_norm(f) for f in candidate_files}
    existing_sources = get_all_sources(col)

    added = modified = deleted = unchanged = 0

    for file_path in candidate_files:
        source = _norm(file_path)
        try:
            content_hash = file_content_hash(file_path)
        except Exception as exc:
            print(f"[ERROR] Cannot hash {file_path}: {exc}")
            continue

        existing_hash = get_existing_hash(col, source)

        if existing_hash is None:
            action = "ADDED"
            added += 1
        elif existing_hash != content_hash:
            action = "MODIFIED"
            modified += 1
        else:
            unchanged += 1
            continue

        print(f"[{action}] {source}")
        _process_file(col, file_path, action, content_hash)

    # Files in DB but no longer on disk → DELETE
    for source in existing_sources - candidate_sources:
        print(f"[DELETED] {source}")
        delete_by_source(col, source)
        deleted += 1

    print(
        f"\n[SYNC COMPLETE] "
        f"added={added}  modified={modified}  deleted={deleted}  unchanged={unchanged}"
    )


def git_diff_sync(base_ref: str, head_ref: str) -> None:
    """Only process files that changed between two git refs (CI fast-path)."""
    print(f"[SYNC] Git-diff sync: {base_ref}..{head_ref}")
    col = get_or_create_collection()

    changed = _git_changed_files(base_ref, head_ref)
    if not changed:
        print("[SYNC] No knowledge files changed — nothing to do.")
        return

    added = modified = deleted = 0

    for file_path, status in changed.items():
        source = _norm(file_path)
        if status == "D":
            print(f"[DELETED] {source}")
            delete_by_source(col, source)
            deleted += 1
        else:
            if not Path(file_path).exists():
                print(f"[WARN] {file_path} reported as {status} but not found on disk — skipping.")
                continue
            try:
                content_hash = file_content_hash(file_path)
            except Exception as exc:
                print(f"[ERROR] Cannot hash {file_path}: {exc}")
                continue
            action = "ADDED" if status == "A" else "MODIFIED"
            print(f"[{action}] {source}")
            _process_file(col, file_path, action, content_hash)
            if action == "ADDED":
                added += 1
            else:
                modified += 1

    print(
        f"\n[SYNC COMPLETE] "
        f"added={added}  modified={modified}  deleted={deleted}"
    )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG-Ops Sync Engine")
    parser.add_argument(
        "--git-diff",
        nargs=2,
        metavar=("BASE", "HEAD"),
        help="Fast-path: only sync files that changed between two git refs.",
    )
    args = parser.parse_args()

    if args.git_diff:
        git_diff_sync(*args.git_diff)
    else:
        full_reconcile()
