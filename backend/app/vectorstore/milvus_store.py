"""
milvus_store.py — All Milvus operations: connect, create collection, upsert, delete, search.
"""
import os
from typing import Optional

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

MILVUS_URI = os.getenv("MILVUS_URI") or os.getenv("ZILLIZ_URI")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN") or os.getenv("ZILLIZ_TOKEN") or os.getenv("ZILLIZ_API_KEY")
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "synced_brain_chunks")
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "1024"))  # Cohere embed-english-v3.0 = 1024


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect() -> None:
    """Open (or reuse) the default Zilliz/Milvus cloud connection."""
    if not MILVUS_URI:
        raise ValueError("MILVUS_URI must be set")

    conn_kwargs = {"uri": MILVUS_URI}
    if MILVUS_TOKEN:
        conn_kwargs["token"] = MILVUS_TOKEN

    connections.connect("default", **conn_kwargs)


# ---------------------------------------------------------------------------
# Schema & collection bootstrap
# ---------------------------------------------------------------------------

def get_or_create_collection() -> Collection:
    """
    Return the Milvus collection, creating it (with HNSW index) if it doesn't exist.
    Always loads the collection into memory before returning.
    """
    connect()

    if utility.has_collection(COLLECTION_NAME):
        col = Collection(COLLECTION_NAME)
        col.load()
        return col

    fields = [
        FieldSchema(name="id",            dtype=DataType.VARCHAR,      max_length=256,  is_primary=True, auto_id=False),
        FieldSchema(name="embedding",     dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM),
        FieldSchema(name="source",        dtype=DataType.VARCHAR,      max_length=512),
        FieldSchema(name="content_hash",  dtype=DataType.VARCHAR,      max_length=64),
        FieldSchema(name="chunk_index",   dtype=DataType.INT64),
        FieldSchema(name="chunk_text",    dtype=DataType.VARCHAR,      max_length=4096),
        FieldSchema(name="last_modified", dtype=DataType.VARCHAR,      max_length=64),
        FieldSchema(name="doc_type",      dtype=DataType.VARCHAR,      max_length=8),
        FieldSchema(name="page",          dtype=DataType.INT64),        # -1 = N/A
    ]
    schema = CollectionSchema(fields, description="Synced Brain RAG chunks")
    col = Collection(COLLECTION_NAME, schema)

    col.create_index(
        field_name="embedding",
        index_params={
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        },
    )
    col.load()
    return col


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def upsert_chunks(col: Collection, chunks: list[dict]) -> None:
    """
    Insert chunk records into Milvus.

    Each dict must contain:
        id, embedding, source, content_hash, chunk_index,
        chunk_text, last_modified, doc_type, page
    """
    if not chunks:
        return

    data = [
        [c["id"]                           for c in chunks],
        [c["embedding"]                    for c in chunks],
        [c["source"]                       for c in chunks],
        [c["content_hash"]                 for c in chunks],
        [c["chunk_index"]                  for c in chunks],
        [c["chunk_text"][:4000]            for c in chunks],   # hard cap
        [c["last_modified"]                for c in chunks],
        [c["doc_type"]                     for c in chunks],
        [c.get("page") if c.get("page") is not None else -1 for c in chunks],
    ]
    col.insert(data)
    col.flush()


def delete_by_source(col: Collection, source: str) -> None:
    """Remove every chunk that belongs to *source* (a file path)."""
    # Escape any double-quotes in the path
    safe = source.replace('"', '\\"')
    col.delete(f'source == "{safe}"')
    col.flush()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_existing_hash(col: Collection, source: str) -> Optional[str]:
    """
    Return the stored content_hash for *source*, or None if the file is unknown.
    """
    safe = source.replace('"', '\\"')
    results = col.query(
        expr=f'source == "{safe}"',
        output_fields=["content_hash"],
        limit=1,
    )
    return results[0]["content_hash"] if results else None


def get_all_sources(col: Collection) -> set[str]:
    """Return all unique file-path strings currently stored in the collection."""
    results = col.query(
        expr='source != ""',
        output_fields=["source"],
        limit=16384,          # adjust if you expect >16 k chunks
    )
    return {r["source"] for r in results}


def search(
    col: Collection,
    query_embedding: list[float],
    top_k: int = 5,
    filter_expr: Optional[str] = None,
) -> list[dict]:
    """
    Run a nearest-neighbour search and return enriched hit dicts.

    Returns:
        list of {source, chunk_text, chunk_index, page, doc_type, score}
    """
    search_params = {"metric_type": "COSINE", "params": {"ef": 64}}
    results = col.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=filter_expr,
        output_fields=["source", "chunk_text", "chunk_index", "page", "doc_type"],
    )
    hits = []
    for hit in results[0]:
        hits.append(
            {
                "source":      hit.entity.get("source"),
                "chunk_text":  hit.entity.get("chunk_text"),
                "chunk_index": hit.entity.get("chunk_index"),
                "page":        hit.entity.get("page"),
                "doc_type":    hit.entity.get("doc_type"),
                "score":       float(hit.score),
            }
        )
    return hits
