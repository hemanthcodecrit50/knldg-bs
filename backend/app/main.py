"""
main.py — Synced Brain FastAPI application.

Endpoints:
  GET  /health  — liveness probe
  POST /query   — RAG query against Milvus + Gemini answer generation
"""
import os
import re
import tempfile
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import cohere
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.app.ingestion.parsers import parse_pdf
from backend.app.sync.sync import sync_deleted_source, sync_single_file
from backend.app.vectorstore.milvus_store import get_or_create_collection, search

# for immediate prototyping
from groq import Groq

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
# immediate prototyping
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

ALLOW_ORIGINS = ["*"]
EMBED_MODEL = "embed-english-v3.0"
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "knowledge")

_REPO_ROOT = Path(__file__).resolve().parents[2]



_collection = None   # lazy-loaded singleton


def get_col():
    global _collection
    if _collection is None:
        _collection = get_or_create_collection()
    return _collection


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up Milvus connection on startup so the first query is fast
    get_col()
    yield


app = FastAPI(title="Synced Brain API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    filters: Optional[dict] = None   # {"source_prefix": "knowledge/ops/", "doc_type": "md"}
    debug: bool = False


class CitationItem(BaseModel):
    source: str
    chunk_index: int
    text: str
    page: Optional[int] = None
    score: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationItem]
    retrieval: Optional[dict] = None


class UploadResponse(BaseModel):
    status: str
    source: str
    action: str
    chunks: int


class UploadFileItem(BaseModel):
    name: str
    source: str
    size_bytes: int
    modified_at: str


class UploadListResponse(BaseModel):
    status: str
    files: list[UploadFileItem]


class DeleteUploadResponse(BaseModel):
    status: str
    source: str
    action: str
    chunks: int


def _slugify_filename_stem(name: str) -> str:
    stem = Path(name).stem.strip().lower()
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-.")
    return stem or "document"


def _build_markdown_from_upload(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp_pdf:
            temp_pdf.write(content)
            temp_pdf.flush()
            pages = parse_pdf(temp_pdf.name)
        if not pages:
            raise ValueError("Uploaded PDF had no extractable text.")

        md_parts: list[str] = []
        for i, page in enumerate(pages, start=1):
            md_parts.append(f"## Page {page.get('page') or i}\n\n{page['text']}")
        return "\n\n".join(md_parts).strip()

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Only UTF-8 text/markdown files and PDFs are supported.")

    if not text.strip():
        raise ValueError("Uploaded file is empty.")
    return text.strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status":f"ok"}


@app.post("/query", response_model=QueryResponse)
def query_brain(req: QueryRequest):
    # 1) Embed the question
    co = cohere.Client(COHERE_API_KEY)

    try:
        resp = co.embed(
            texts=[req.question],
            model=EMBED_MODEL,
            input_type="search_query",
        )
        query_embedding: list[float] = resp.embeddings[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")

    # 2) Build optional Milvus filter expression
    filter_expr: Optional[str] = None
    if req.filters:
        parts: list[str] = []
        if prefix := req.filters.get("source_prefix"):
            safe = prefix.replace('"', '\\"')
            parts.append(f'source like "{safe}%"')
        if doc_type := req.filters.get("doc_type"):
            safe = doc_type.replace('"', '\\"')
            parts.append(f'doc_type == "{safe}"')
        if parts:
            filter_expr = " and ".join(parts)

    # 3) Vector search
    col = get_col()
    try:
        hits = search(col, query_embedding, top_k=req.top_k, filter_expr=filter_expr)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}")

    if not hits:
        return QueryResponse(
            answer="No relevant information found in the knowledge base.",
            citations=[],
        )

    # 4) Build context for LLM
    context_blocks = [
        f"[{i + 1}] Source: {h['source']}\n{h['chunk_text']}"
        for i, h in enumerate(hits)
    ]
    context = "\n\n---\n\n".join(context_blocks)

    # prompt = (
    #     "You are a helpful assistant with access to a personal knowledge base.\n"
    #     "Answer the question using ONLY the provided context. "
    #     "Be concise and factual. If the answer is not in the context, say so.\n\n"
    #     f"Context:\n{context}\n\n"
    #     f"Question: {req.question}\n\nAnswer:"
    # )

    prompt = (
        "You are a strict retrieval-based assistant.\n"
        "Use ONLY the provided context.\n"
        "Do NOT copy text verbatim.\n"
        "Summarize and synthesize information clearly.\n"
        "If the answer is not present, say: 'Not found in knowledge base.'\n"
        "Use citations like [1], [2] when referring to sources.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {req.question}\n\nAnswer:"
    )
    hits = search(col, query_embedding, top_k=req.top_k, filter_expr=filter_expr)
    # Filter low-quality results
    hits = [h for h in hits if h["score"] > 0.5]

    # # 5) Gemini reasoning
    # try:
    #     client = genai.Client(api_key=GOOGLE_API_KEY)

    #     response = client.models.generate_content(
    #         model="gemini-2.0-flash",
    #         contents=prompt,
    #     )
    #     answer = response.text.strip()
    # except Exception as exc:
    #     answer = f"LLM error ({exc}). Retrieved {len(hits)} chunks — see citations."



    # 5 Grok reasoning
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            # model="llama-3.1-70b-versatile"  if needed more on ROI
            messages=[
                {"role": "system", "content": "Answer using only the provided context."},
                {"role": "user", "content": prompt},
            ],
        )

        answer = response.choices[0].message.content.strip()

    except Exception as exc:
        answer = f"LLM error ({exc}). Retrieved {len(hits)} chunks — see citations."



    # 6) Build citations
    citations = [
        CitationItem(
            source=h["source"],
            chunk_index=h["chunk_index"],
            text=h["chunk_text"],
            page=h["page"] if h.get("page") and h["page"] != -1 else None,
            score=round(h["score"], 4) if req.debug else None,
        )
        for h in hits
    ]

    retrieval_info = (
        {"top_k": req.top_k, "scores": [round(h["score"], 4) for h in hits]}
        if req.debug
        else None
    )

    return QueryResponse(answer=answer, citations=citations, retrieval=retrieval_info)


@app.post("/upload", response_model=UploadResponse)
async def upload_knowledge_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in upload.")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".md", ".txt", ".pdf"}:
        raise HTTPException(status_code=400, detail="Supported file types: .md, .txt, .pdf")

    try:
        payload = await file.read()
        markdown_text = _build_markdown_from_upload(file.filename, payload)

        uploads_dir = (_REPO_ROOT / KNOWLEDGE_DIR / "uploads").resolve()
        uploads_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        safe_stem = _slugify_filename_stem(file.filename)
        target_path = uploads_dir / f"{safe_stem}-{ts}.md"

        target_path.write_text(markdown_text + "\n", encoding="utf-8")

        sync_result = sync_single_file(str(target_path))
        return UploadResponse(
            status="ok",
            source=sync_result["source"],
            action=sync_result["action"],
            chunks=sync_result["chunks"],
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


@app.get("/uploads", response_model=UploadListResponse)
def list_uploads():
    try:
        uploads_dir = (_REPO_ROOT / KNOWLEDGE_DIR / "uploads").resolve()
        uploads_dir.mkdir(parents=True, exist_ok=True)

        items: list[UploadFileItem] = []
        for p in sorted(uploads_dir.glob("*.md"), reverse=True):
            stat = p.stat()
            source = Path(KNOWLEDGE_DIR) / "uploads" / p.name
            items.append(
                UploadFileItem(
                    name=p.name,
                    source=source.as_posix(),
                    size_bytes=stat.st_size,
                    modified_at=datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                )
            )

        return UploadListResponse(status="ok", files=items)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Listing uploads failed: {exc}")


@app.delete("/uploads/{filename}", response_model=DeleteUploadResponse)
def delete_upload(filename: str):
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if Path(safe_name).suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown uploads can be deleted.")

    uploads_dir = (_REPO_ROOT / KNOWLEDGE_DIR / "uploads").resolve()
    target = (uploads_dir / safe_name).resolve()

    try:
        target.relative_to(uploads_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path.")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Upload file not found.")

    try:
        target.unlink()
        source = (Path(KNOWLEDGE_DIR) / "uploads" / safe_name).as_posix()
        sync_result = sync_deleted_source(source)
        return DeleteUploadResponse(
            status="ok",
            source=sync_result["source"],
            action=sync_result["action"],
            chunks=sync_result["chunks"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
