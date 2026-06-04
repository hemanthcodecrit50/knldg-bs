# Knowledge Base — Getting Started

Welcome to your **Synced Brain** knowledge base. This folder is the single source of truth for everything your AI knows.

## How it works

Any Markdown (`.md`) or PDF (`.pdf`) file you place here will be automatically ingested into the configured vector database (compatible with Milvus, e.g. Zilliz Cloud) every time you push to `main`. The system will:

1. **Detect** whether the file is new, modified, or deleted using a SHA-256 content hash.
2. **Chunk** the text into overlapping segments (800 chars, 100-char overlap).
3. **Embed** each chunk with Cohere `embed-english-v3.0`.
4. **Upsert** the vectors into the configured vector store (Milvus-compatible) with deterministic IDs so there are never duplicates.

Deleted files are automatically removed from the vector store — no stale data, ever.

## Folder structure suggestions

```
knowledge/
├── README.md           ← this file
├── projects/           ← notes on ongoing projects
├── ops/                ← runbooks, infrastructure docs
├── research/           ← papers, reading notes
└── personal/           ← anything else
```

You can filter queries to a specific sub-folder using the `source_prefix` option in the UI sidebar.

## Tips

- **Use clear headings** — the chunker respects Markdown structure.
- **One idea per file** is often better than one giant file.
- **PDF page numbers** are preserved in citations so you can jump straight to the source.
